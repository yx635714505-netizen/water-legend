param(
 [ValidateSet('init','submit','status','start','run','stop','cancel')][string]$Action='status',
 [string]$Package,[string]$Name,[string]$JobId
)
$ErrorActionPreference='Stop'
$PoolRoot=$PSScriptRoot
$Config=Get-Content -LiteralPath "$PoolRoot\config.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$Utf8=New-Object System.Text.UTF8Encoding($false)
$StateFile="$PoolRoot\state.json"
$PowerShellExe="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
function AtomicJson($Path,$Value) {
 $tmp=$Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
 [IO.File]::WriteAllText($tmp,($Value|ConvertTo-Json -Depth 20),$Utf8)
 if(Test-Path -LiteralPath $Path){[IO.File]::Replace($tmp,$Path,($Path+'.bak'))}else{[IO.File]::Move($tmp,$Path)}
}
function Locked([scriptblock]$Body) {
 $m=New-Object Threading.Mutex($false,'Local\CodexCAD_PoolState');$held=$false
 try {try{$held=$m.WaitOne(30000)}catch [Threading.AbandonedMutexException]{$held=$true};if(!$held){throw 'Queue lock timeout'};& $Body}finally{if($held){$m.ReleaseMutex()};$m.Dispose()}
}
function Read-State {
 if(Test-Path -LiteralPath $StateFile){return Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json}
 return [pscustomobject]@{schema=1;jobs=@()}
}
function Save-State($State){AtomicJson $StateFile $State}
function Read-Json($Path){Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json}
function Live-Launcher($Job) {
 if(!$Job.launcherPid){return $false}
 $p=Get-Process -Id $Job.launcherPid -ErrorAction SilentlyContinue
 return $p -and $p.ProcessName -eq 'HiddenCad' -and $p.StartTime.ToUniversalTime().ToString('o') -eq $Job.launcherStarted
}
function Set-WorkerProfile($Slot,$JobRoot) {
 $profile=$Config.profilePrefix+$Slot;$reg=$Config.registryProfiles+'\'+$profile
 if(!(Test-Path -LiteralPath $reg)){throw "Missing profile: run init first ($profile)"}
 $general=$reg+'\General';$vars=$reg+'\Variables'
 $editor=$reg+'\Editor Configuration'
 Set-ItemProperty -LiteralPath $editor -Name LogFilePath -Value "$JobRoot\logs"
 Set-ItemProperty -LiteralPath $editor -Name SaveFilePath -Value "$JobRoot\autosave"
 $baseTrust=(Get-ItemProperty -LiteralPath ($Config.registryProfiles+'\'+$Config.profileSource+'\Variables')).TRUSTEDPATHS
 Set-ItemProperty -LiteralPath $vars -Name TRUSTEDPATHS -Value ($baseTrust+';'+$PoolRoot+'\bin;'+$JobRoot+'\scripts')
 foreach($kv in @{TempDirectory="$JobRoot\temp\";SaveFilePath="$JobRoot\autosave\";ACADLOGFILE="$JobRoot\logs\acad.log";PlotLogPath="$JobRoot\logs\";PrinterConfigDir="$PoolRoot\workers\$Slot\plotters";PrinterDescDir="$PoolRoot\workers\$Slot\plotters\PMP Files";PrinterStyleSheetDir="$PoolRoot\workers\$Slot\plotters\Plot Styles";ProfileStorage="$PoolRoot\workers\$Slot\profile.aws"}.GetEnumerator()) {Set-ItemProperty -LiteralPath $general -Name $kv.Key -Value $kv.Value}
 return $profile
}
function Launch-Job($Job,$Slot) {
 $root=$Job.root;$profile=Set-WorkerProfile $Slot $root
 $boot=@('FILEDIA','0','CMDDIA','0',('(command "_.NETLOAD" "'+($PoolRoot.Replace('\','/'))+'/bin/CadPoolBridge.dll")'),'CADPOOLREADY','_.SCRIPT',('"'+($root.Replace('\','/'))+'/scripts/command.scr"'),'') -join "`r`n"
 [IO.File]::WriteAllText("$root\scripts\boot.scr",$boot,[Text.Encoding]::GetEncoding(936))
 AtomicJson "$root\launch.json" @{slot=$Slot;jobId=$Job.id;profile=$profile;acadExe=$Config.acadExe;template=$Config.template;timeoutSeconds=$Config.jobTimeoutSeconds}
 $p=Start-Process -FilePath "$PoolRoot\bin\HiddenCad.exe" -ArgumentList ('"'+$root+'"') -WorkingDirectory $root -WindowStyle Hidden -PassThru
 $Job.status='running';$Job.slot=$Slot;$Job.launcherPid=$p.Id;$Job.launcherStarted=$p.StartTime.ToUniversalTime().ToString('o');$Job.startedUtc=[datetime]::UtcNow.ToString('o')
}
function Tick {
 Locked {
  $state=Read-State
  foreach($job in @($state.jobs|Where-Object {$_.status -in @('running','stopping','blocked')})) {
   $control=$job.root+'\control';$elapsed=([datetime]::UtcNow-[datetime]::Parse($job.startedUtc).ToUniversalTime()).TotalSeconds
   if(Test-Path -LiteralPath "$control\exit.json") {
    $exit=Read-Json "$control\exit.json";$result=$null
    if(Test-Path -LiteralPath "$control\result.json"){$result=Read-Json "$control\result.json"}
    $process=Read-Json "$control\process.json"
    $ready=$null;if(Test-Path -LiteralPath "$control\ready.json"){$ready=Read-Json "$control\ready.json"}
    $identity=$ready -and $ready.jobId -eq $job.id -and $ready.pid -eq $process.pid -and $ready.slot -eq $job.slot -and $ready.profile -eq ($Config.profilePrefix+$job.slot)
    $ok=$identity -and $result -and $result.jobId -eq $job.id -and $result.pid -eq $process.pid -and $result.success -and $exit.jobId -eq $job.id -and !$exit.terminated -and $exit.exitCode -eq 0
    $job.status=if($ok){'succeeded'}elseif($job.cancelRequested){'cancelled'}else{'failed'}
    $job.message=if($exit.terminated){'CAD was stopped or timed out; completion was not accepted'}elseif($result){$result.message}else{'CAD exited without a validated completion report'}
    $job.finishedUtc=[datetime]::UtcNow.ToString('o');continue
   }
   if(!(Live-Launcher $job)) {
    if(!$job.launcherPid -and (Test-Path -LiteralPath "$control\launcher.json")) {
     $receipt=Read-Json "$control\launcher.json";$job.launcherPid=$receipt.pid;$job.launcherStarted=$receipt.started
     if(Live-Launcher $job){continue}
    }
    if(!$job.launcherPid -and $elapsed -lt $Config.startupTimeoutSeconds){continue}
    # Never free a slot while its CAD might still be alive. Only stop the exact boot command owned here.
    if(Test-Path -LiteralPath "$control\process.json") {
     $proc=Read-Json "$control\process.json"
     $live=Get-CimInstance Win32_Process -Filter ("ProcessId = "+[int]$proc.pid)
     if($live -and $live.Name -eq 'acad.exe' -and $live.CommandLine.Contains($job.root+'\scripts\boot.scr')) {Stop-Process -Id $proc.pid -Force; $job.status='blocked';$job.message='Launcher lost; stopping owned CAD before releasing slot';continue}
     if($live -and $live.Name -eq 'acad.exe'){$job.status='blocked';$job.message='Ownership could not be verified; slot held';continue}
    }
    $job.status='failed';$job.message='Launcher exited unexpectedly';$job.finishedUtc=[datetime]::UtcNow.ToString('o');continue
   }
   if(Test-Path -LiteralPath "$control\ready.json") {
    $ready=Read-Json "$control\ready.json";$proc=Read-Json "$control\process.json"
    if($ready.jobId -ne $job.id -or $ready.pid -ne $proc.pid -or $ready.slot -ne $job.slot){$job.message='Worker identity mismatch';$job.status='stopping';[IO.File]::WriteAllText("$control\stop.request",'identity mismatch')}
   }elseif($elapsed -gt $Config.startupTimeoutSeconds){$job.message='Native CAD startup timed out';$job.status='stopping';[IO.File]::WriteAllText("$control\stop.request",'startup timeout')}
   if(Test-Path -LiteralPath "$control\result.json") {
    $age=([datetime]::UtcNow-(Get-Item -LiteralPath "$control\result.json").LastWriteTimeUtc).TotalSeconds
    if($age -gt $Config.exitTimeoutSeconds){$job.message='CAD did not close after completion';$job.status='stopping';[IO.File]::WriteAllText("$control\stop.request",'exit timeout')}
   }
  }
  $busy=@($state.jobs|Where-Object {$_.status -in @('running','stopping','blocked')}|ForEach-Object {$_.slot})
  for($i=1;$i -le $Config.maxWorkers;$i++) {
   $slot='W{0:d2}' -f $i
   if($slot -in $busy){continue}
   $next=$state.jobs|Where-Object status -eq 'queued'|Select-Object -First 1
   if(!$next){break}
   # Persist slot ownership before launching, so a dispatcher restart cannot duplicate a job.
   $next.status='running';$next.slot=$slot;$next.startedUtc=[datetime]::UtcNow.ToString('o');Save-State $state
   try{Launch-Job $next $slot}catch{$next.status='failed';$next.message=$_.Exception.ToString();$next.finishedUtc=[datetime]::UtcNow.ToString('o')}
   Save-State $state
  }
  Save-State $state
 }
}
switch($Action) {
 'init' {
  Locked {
   $state=Read-State
   if(@($state.jobs|Where-Object {$_.status -in @('running','stopping','blocked')}).Count){throw 'Cannot initialize while CAD jobs are active'}
   foreach($d in @('bin','jobs','workers','logs')){New-Item -ItemType Directory -Path "$PoolRoot\$d" -Force|Out-Null}
   $compiler="$env:SystemRoot\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
   & $compiler /nologo /target:exe /platform:x64 /r:System.Web.Extensions.dll "/out:$PoolRoot\bin\HiddenCad.exe" "$PoolRoot\HiddenCad.cs"
   if($LASTEXITCODE){throw 'Launcher compilation failed'}
   $acadDir=Split-Path $Config.acadExe
   & $compiler /nologo /target:library /platform:x64 /r:System.Web.Extensions.dll /r:System.Windows.Forms.dll "/r:$acadDir\acmgd.dll" "/r:$acadDir\acdbmgd.dll" "/r:$acadDir\accoremgd.dll" "/out:$PoolRoot\bin\CadPoolBridge.dll" "$PoolRoot\CadPoolBridge.cs"
   if($LASTEXITCODE){throw 'Native bridge compilation failed'}
   $source=$Config.registryProfiles+'\'+$Config.profileSource
   $plotters=(Get-ItemProperty -LiteralPath ($source+'\General')).PrinterConfigDir
   for($i=1;$i -le $Config.maxWorkers;$i++) {
    $slot='W{0:d2}' -f $i;$dest=$Config.registryProfiles+'\'+$Config.profilePrefix+$slot
    if(!(Test-Path -LiteralPath $dest)){Copy-Item -LiteralPath $source -Destination $dest -Recurse}
    New-Item -ItemType Directory -Path "$PoolRoot\workers\$slot" -Force|Out-Null
    if(!(Test-Path -LiteralPath "$PoolRoot\workers\$slot\plotters")){Copy-Item -LiteralPath $plotters -Destination "$PoolRoot\workers\$slot\plotters" -Recurse}
   }
   Save-State $state
  }
  "Initialized: $($Config.maxWorkers) worker slots, at most $($Config.maxOutstandingJobs) unfinished jobs."
 }
 'submit' {
  if(!$Package){throw 'Supply -Package containing job.json and scripts/command.scr'}
  $source=(Resolve-Path -LiteralPath $Package).Path
  if(@(Get-ChildItem -LiteralPath $source -Recurse -Force|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Package must not contain junctions or symbolic links'}
  $manifest=Read-Json "$source\job.json"
  if(!(Test-Path -LiteralPath "$source\scripts\command.scr")){throw 'Missing scripts/command.scr'}
  if(!$manifest.validationReport -or !$manifest.expectedOutputs -or $manifest.isolationContract -ne 1){throw 'Manifest must specify validationReport, expectedOutputs, isolationContract=1'}
  foreach($p in @($manifest.validationReport)+@($manifest.expectedOutputs)){if([IO.Path]::IsPathRooted($p) -or $p -match '(^|[\\/])\.\.([\\/]|$)'){throw 'Output/report paths must stay inside job directory'}}
  Locked {
   $state=Read-State;$count=@($state.jobs|Where-Object {$_.status -in @('queued','running','stopping','blocked')}).Count
   if($count -ge $Config.maxOutstandingJobs){throw 'Queue full: 5 unfinished jobs already submitted; retry after one completes'}
   $id=[guid]::NewGuid().ToString('N');$root="$PoolRoot\jobs\$id"
   New-Item -ItemType Directory -Path $root|Out-Null
   # Copy only package inputs and scripts. Never accept stale result/control files.
   foreach($d in @('input','scripts')){if(Test-Path -LiteralPath "$source\$d"){Copy-Item -LiteralPath "$source\$d" -Destination "$root\$d" -Recurse}}
   foreach($d in @('input','scripts','control','work','output','logs','temp','autosave')){New-Item -ItemType Directory -Path "$root\$d" -Force|Out-Null}
   $manifest|Add-Member -NotePropertyName jobId -NotePropertyValue $id -Force
   AtomicJson "$root\job.json" $manifest

   $job=[pscustomobject]@{id=$id;name=$Name;root=$root;status='queued';slot=$null;launcherPid=0;launcherStarted=$null;submittedUtc=[datetime]::UtcNow.ToString('o');startedUtc=$null;finishedUtc=$null;message=$null;cancelRequested=$false}
   $state.jobs=@($state.jobs)+@($job);Save-State $state;$job|ConvertTo-Json
  }
 }
 'status' {
  Locked {$state=Read-State;@{maxWorkers=$Config.maxWorkers;maxOutstandingJobs=$Config.maxOutstandingJobs;jobs=@($state.jobs)}|ConvertTo-Json -Depth 10}
 }
 'start' {
  $mutex=New-Object Threading.Mutex($false,'Local\CodexCAD_PoolDaemon');$held=$false
  try{try{$held=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$held=$true};if(!$held){'Dispatcher already running';break}}finally{if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
  if(Test-Path -LiteralPath "$PoolRoot\stop-daemon.request"){Remove-Item -LiteralPath "$PoolRoot\stop-daemon.request"}
  $p=Start-Process -FilePath $PowerShellExe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Action run') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$PoolRoot\logs\dispatcher.out.log" -RedirectStandardError "$PoolRoot\logs\dispatcher.err.log"
  "Dispatcher started: $($p.Id)"
 }
 'run' {
  $mutex=New-Object Threading.Mutex($false,'Local\CodexCAD_PoolDaemon');$held=$false
  try {
   try{$held=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$held=$true};if(!$held){exit 0}
   AtomicJson "$PoolRoot\dispatcher.json" @{pid=$PID;startedUtc=[datetime]::UtcNow.ToString('o')}
   while(!(Test-Path -LiteralPath "$PoolRoot\stop-daemon.request")){try{Tick}catch{Add-Content -LiteralPath "$PoolRoot\logs\errors.log" -Value ([datetime]::UtcNow.ToString('o')+' '+$_.Exception.ToString())};Start-Sleep -Seconds 2}
  }finally{if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
 }
 'stop' {[IO.File]::WriteAllText("$PoolRoot\stop-daemon.request",'stop scheduling; running launchers remain supervised');'Dispatcher stop requested; running CAD jobs are not killed.'}
 'cancel' {
  Locked {$state=Read-State;$job=$state.jobs|Where-Object id -eq $JobId;if(!$job){throw 'Unknown job'}
   if($job.status -eq 'queued'){$job.status='cancelled';$job.finishedUtc=[datetime]::UtcNow.ToString('o')}
   elseif($job.status -in @('running','stopping','blocked')){$job.cancelRequested=$true;$job.status='stopping';[IO.File]::WriteAllText(($job.root+'\control\stop.request'),'cancel')}
   Save-State $state
  }
 }
}
