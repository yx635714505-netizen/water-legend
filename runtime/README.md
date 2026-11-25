# 跨机出图与验收

## 逐层立管碰撞检查

绘图前由建筑原图及给排水系统编制 `riserStoreys`（全部楼层）和 `riserPlans`（每个核对区的应有立管）。各户编号在同一区域须可区分。独立列应有数量、轴位和设备段，再生成绘图操作。坐标均为完成排版后的模型毫米，管外径取项目选用管材的外径，安装净距按项目填写。下面数值仅用于说明字段。

```json
{
  "riserStoreys": ["首层"],
  "riserPlans": [{
    "floor": "首层", "layout": "水施 06 首层给排水平面图", "sourceRef": "建施一层平面 4/F 轴，给水系统 JG-1",
    "risers": [{"number":"JG-1","layer":"VPIPE-给水","at":[1600,2500],"outerDiameter":50,"clearance":15}]
  }]
}
```

每张平面均须入表。同页多层分列实际 `window: [左,下,右,上]`；免出图层填 `layout: null`、`omissionReason`，在出图框外保留本层建筑和立管核对窗口。实际无立管填空数组及 `emptyReason`。屋顶等确无墙柱时，须对照建筑图并写明 `noBarrierSource` 的图号和位置。建筑使用自定义墙柱层时在任务顶层填 `barrierLayers`。对照原图检查成品是否漏墙、漏柱，包括普通线绘成的柱。零散边线、未解析的建筑对象须先补全可验的墙柱轮廓。曲线或不规则实体的包围范围可能保守，疑似相交须以精确轮廓复核后再验。已设计预埋的雨水管，在该管条目填 `embeddedHost` 指定最终宿主的实例句柄路径。

后台重开成品生成 `output/riser-geometry.json`。`verify` 逐层匹配清单与原生对象，从管外缘核算净距，输出 `output/riser-audit.json`。每层列应查数、实查数，每个匹配管位列最近墙柱、净距及冲突。准备核对表前先执行 `verify`。对照原图和模型，在 `riserFloorReviews` 逐层记录查过的编号、墙柱范围、预埋依据和无管层情况。清单、建筑原图、实际成品和本次几何核验结果随核对表绑定。`deliver` 重新执行相同检查，任何未通过项都会阻止写出 DWG。两张随库设备试印样张仅用于环境校准。

## 所有项目共用的出图配置

整套图纸的 `frames[].b` 按两列竖排布置。各页使用建筑图框块时，`frames[].frameBlock` 填写本页实际插入的图框块名，对应 `bases[].name`。准备任务时检查分列、顶边及图序，成品重开后核对实际视口中心，并按块名回读模型图框边界。逐页试印后再看整套模型总览。

正式生成先将[水施通用底板](../assets/baseplate/水施通用底板.dwg)复制到任务目录，再打开工作副本。底板保留原生专业配置 TCH_DBPSCONFIG，模型空间为空。prepare 校验底板 SHA-256，verify 在交付图上回读配置类型和 DN200 平面污水管的原生图形宽度。标准标样覆盖给水、污水、废水、雨水平面和系统管段。

建筑 DWG 提供本项目的几何、户别、图框和设备位置。生成器从技能的线型母版取原生对象，用 `drawing-profile.json` 固定模型和布局显示。该配置规定 `MSLTSCALE=0`、`PSLTSCALE=1`、`LWDISPLAY=1`。线型定义、按层颜色和实体覆盖仍按母版。项目绘图脚本只生成项目清单和几何，正式任务用当前技能重新 prepare，避免复用历史任务包里的 Engine.dll。核对整页版式时对照[首层排版预览](baseline/洲口蘭園-首层排版.png)和[系统排版预览](baseline/洲口蘭園-系统排版.png)。首次试印按下文与两页标准 PDF 比较。图框、设备及给水系统形式取本项目实际条件。

后台生成后，`verify` 比较源线型母版的 SHA-256、成品管对象的图层颜色及线型、实体线宽、模型和每个布局的显示变量。房间服务清单的系统接口需要原生引出标注。默认检查系统端点；引线起于阀门或合画接口时，给该条 service 填 `systemLeaderPoint`，取实际阀门或接口的模型坐标，并在试印中核对房间名和合画范围。

正式交付执行以下步骤。由绘图者完成逐页复核和记录，无需另设用户批准环节。

```powershell
python runtime/water.py verify $job.root
python runtime/water.py review-template $job.root $reviewPath
# 对照本次图纸填写 $reviewPath 后，交付到一个新文件名
python runtime/water.py deliver $job.root $reviewPath $destinationDwg
```

核对表自动绑定本项目的建筑 DWG、成品 DWG 和每张试印 PDF。每张填写 `layoutReview`，记录实际核过的图名、图签、版面和引注避让。平面另填 `baseComparison`（按轴网与建筑原图叠合；写明保留的墙柱、门窗、尺寸链和清掉的细部）和 `colorAndLineReview`（彩色模型与实印的具体管段、线宽、线型节距）。系统图另填 `leaderReview` 和 `colorAndLineReview`，核对端点、文字、楼层线及管径。发现问题先修订，再用新试印复核。工程判断与视觉对照需要实际看图；文件校验用于防止漏页或误用旧版记录。

### 平面底图的彩色验收记录

重开最终 DWG，按每张实际平面的模型范围输出彩色 PNG，保留建筑和专业线的真实颜色。将整页图放在任务包 `output/model-color-N.png`，N 与同页 `pageN.pdf` 的零起始序号一致。先保存彩色图，再执行 `review-template`，核对表将记录各图的 SHA-256。交付机的 Python 需要 Pillow 读取 PNG。

逐页按[成品底图逐页验收](../references/出图版式与底图清理规则.md#成品底图逐页验收)检查。在 `openingReview.locations` 写实查楼层、轴网或房间范围，在 `components` 写窗框、玻璃线、门扇及开启线的实际显示和几何完整性。全部符合时将 `result` 填为“通过”；整页原图确无门窗时填“原图无门窗”，同时说明原图依据和成品检查结果。存在残色或漏检时保留问题记录并修订。更换 DWG、彩色图或试印后重新核对并生成对应记录。

`verify` 执行成品对象和配置回读，`deliver` 另检查平面清单、彩色图文件、哈希和逐页签核结论。门窗实际颜色须由出图者在重开的成品中逐处判读。

## Windows 工作机准备

在克隆目录打开 PowerShell。准备 Python 3.8 或更高版本、64 位 AutoCAD 2020、匹配的天正 T20 V8.0 原生模块、Windows .NET Framework 4.x 编译器、中文字体及项目打印样式。启动器从本机 CAD 安装目录引用托管 DLL，原生管道与文字接口对应上述天正版本。PDF 试印工具使用 A3 横幅、DWG To PDF.pc3 与 monochrome.ctb。项目有其他纸幅、CTB 或版本时，应按目标机和实际项目适配并试印。

已有共用 CAD 池时，沿用其入口。首次部署后台池时，把本库的池源码复制到独立的可写运行目录，按目标 Windows 账号核对 config.json 中的 acadExe、template、registryProfiles、profileSource。源 Profile 应已能显示天正对象并正常打印。init 会编译启动器、创建该账号的专用 CAD Profile 和打印配置副本。下面的示例假设当前目录是仓库根目录。

```powershell
$poolHome = Join-Path $env:LOCALAPPDATA 'WaterCadPool'
Copy-Item -LiteralPath runtime/cad-pool -Destination $poolHome -Recurse
$pool = Join-Path $poolHome 'pool.ps1'
# 按本机安装位置调整 $poolHome/config.json 后执行
& $pool -Action init
& $pool -Action start
```

上面的复制步骤用于首次安装。已有池请将 $pool 指向其 pool.ps1。任务数据、CAD 进程和临时文件由运行目录管理，仓库可单独 git pull 更新。更新池源码时先待现有任务完成，再停止该池、更新源码并重新 init/start，保留本机配置。

## 首次试印

在仓库外选一个尚未使用的任务包目录。Python 入口接受 --acad 和 --tangent，用于指定 CAD DLL 和天正 ARX 所在目录。生成脚本随任务包编译，使用独立后台 CAD 实例。

```powershell
$pkg = Join-Path $env:TEMP ('water-check-' + [guid]::NewGuid())
python runtime/water.py prepare runtime/commission.json $pkg
$job = & $pool -Action submit -Package $pkg -Name '水施原生绘图校验' | ConvertFrom-Json
(& $pool -Action status | ConvertFrom-Json).jobs | Where-Object id -eq $job.id
# 此任务显示 succeeded 后执行
python runtime/water.py check-baseline $job.root
```

运行基准比较的 Python 解释器需安装 `pypdfium2`（`python -m pip install pypdfium2`）。命令先执行成品回读，再用同一渲染器比较两张试印与随库 PDF 的纸面尺寸及 144 dpi 灰度像素。记录 Git 提交和结果。出现差异时核对 CAD、天正、字体、CTB、PC3 与纸型并重新试印。基准 PDF 随技能版本管理。

打开该任务 output/page0.pdf 和 page1.pdf，按图对照给水管与标径、立管、露台墙侧排、阀门、系统管段、引注、坡度、标高和图名。验收记录应包括实际使用的 Git 提交、CAD 与天正版本、试印件和读回结果。

## 新项目实施顺序

1. **读建筑原图。** 先对照平面、剖面和屋面，记录各户、各层轴网基点、完成面、房间用途、器具、洞口、管井和室外条件。用下面的 inspect 命令建立读图任务包，再经同一个池提交。output/architecture.json 按块定义记录对象类型、句柄、范围、文字、管径、原生夹点和块参照变换。嵌套对象按逐级变换还原到所在平面。对照建筑试印确认墙面、图签、雨水口和朝向。
2. **建立本项目清单。** 逐户列出每层水源→JL→各房间阀门、污水→井→化粪池、实际厨房废水→独立出户、各汇水点→雨水立管→去向。按轴网叠合每根立管，注明实际转接层。系统图与平面共用这份编号和端点清单。复核不同分户之间的独立性、房间数、阀门数和系统接口数。
3. **准备图纸版式。** 从项目建筑图读取图框、签名和标题；目录、说明及图签字段用 `layout` 母版，选择集见 `assets/layout-v2/manifest.json`。单项图例和设备从 `pot` 母版取用，索引见 `assets/legend-catalog.json`，设备原型见 `production_symbols`。按各自索引核对文件及 SHA-256。在项目说明副本中改写工程名称、材料、接驳和参数。各楼层底图只选择需保留的对象。底图块的嵌套内容和打印效果均须检查。
4. **绘制并试印。** 将上述资料整理成项目自己的 JSON 文件，坐标以模型空间毫米计；用 prepare、submit、verify 执行。原生对象和引注来源、管段端点、纸面字高、阀体净空和跨层给排水连接均按专业规则填写。程序仅落实输入方案，项目房间识别、设计取点和避让由出图者逐层完成。
5. **对最终 DWG 复核。** 先核对 output/aud.json 中读回的管径、线型、坐标、接口和引注，再检查每张 PDF；必要时在独立后台 CAD 中重开核对。逐张检查图框、人员、图签比例、文字遮挡、阀门压墙、叠线、标高、坡度、侧排贴墙及室外实际去向。屋面标高用建筑穿出点实测值，立管与转换层逐编号对照。针对本项目增加给水阀后接口计数、排水上下游、楼层连续尺寸等专项校核。修订后重新提交新任务包并保留本轮证据。

```powershell
python runtime/water.py prepare D:/project/architecture.dwg D:/project/read-01 --inspect
python runtime/water.py prepare D:/project/design.json D:/project/build-01
```

## 绘图清单字段

以 commission.json 的结构为起点。坐标、图层、用水点、户数、管径、层高与纸幅比例均由当前项目确定。不同用途源 DWG 的符号句柄按对应文件单独取样。

| 字段 | 用法 |
| --- | --- |
| sources | 对象名到 {path, sha256} 的映射，路径相对于本项目 JSON。可指定建筑底图、已编辑的说明页副本和额外符号母版。工具自带 baseplate、style、side、pot 和 layout。 |
| bases | 每项含 source、ids（同一源图中的实体句柄）、name（唯一块名）、dx、dy、fade。可选 scale 为模型原点等比缩放系数（默认 1），dx、dy 为缩放后至图幅的平移量；建筑底图可用 fade，图签和说明页保留原样。可选 text 用源句柄映射所选 DBText/TCH_TEXT 的项目文字。需分别编辑的嵌套字段、图签属性和复杂排版，在项目副本中预先处理。 |
| symbols | 用自定义名称映射 {source, handle}。墙侧排样本名为 SIDE_LEFT、SIDE_RIGHT，清扫口、检查井、池体为 CLEAN、WELL、POT，顶入雨水斗为 BOWL。校对接点、原生类型、原型图层和朝向。 |
| frames | 依出图顺序列出各页 name、模型边界 b=[左,下,右,上]、比例分母 scale。本入口适配横向 A3，1:100 对应 42000×29700。建筑图框实体需在 bases 中显式放置。 |
| ops | t 为操作类型，h 为样本名，a 为起点或安装点。p 是原生管段，另给 b、dn、show，可指定 label；s 是符号，可指定夹点 idx、旋转弧度 rot、layer、立管 dn 或井号 txt；l 为天正引注，a 指向对象，b 是文字基线起点，填 txt、txt2、left、layer，选同方向样本；d 是天正两点竖向尺寸；n 为原生文字；title 为天正图名；line 采用所选普通直线样本。引注、标高和坡度使用对应原生对象类型和样本。 |
| 管段样本 | J/W/F/Y 分别表示给水、污水、废水、雨水，PLAN/SYS/DOT 对应平面管、系统管、立管点。按系统选择，其他用途从本库线型 DWG 另行核定，不直接代用。 |
| dimensions | 每条楼层连续尺寸给 x、labelX 和由低到高的实际完成面绝对坐标 levels，使用天正连续尺寸命令，当场检查生成的原生夹点。 |
| connections | 在管段设置 network；在此按每户、每层、每一路列 network、from 和 to（所有待核接口坐标的数组）。校核使用保存重开后的管段几何。绘图者应将清单与实际建筑点位逐一核对。 |
| services | 给实际绘制的接口操作设置唯一 id，每个房间接口填一条 plan、system（两个操作 id）与 planPoint、systemPoint（按两图独立量取的坐标）；需要时给 planGrip、systemGrip 指定夹点序号。重开后核对每个接口的位置，并查出多个房间误用同一个端头的情况。同条件合画时另按实际数量与编号核对。 |
| clearances | 每项填待核阀体或立管的操作 id、所需净距离 margin，以及在同一坐标系中从建筑图取出的墙柱或柜体矩形 obstacles=[[左,下,右,上],…]。以重开后的完整对象范围检查净距离；斜墙及非矩形净空需用项目几何单独复核。 |

## 历次出图中应继承的校核经验

- 平面上每户、每层的实际阀后端头先从建筑图列清单，再去系统图逐个认领。两间房共用一个无数量引注曾造成统计通过而实际漏画。房间用途、编号、数量与引线落点都要能在成图上找到。
- 立管中心和管段端点与设计配置一致，只能证明绘图执行正确。把建筑墙、柱、门洞、洁具和柜体叠上来，用立管外缘、阀体及检修空间复核。逐张查完首层、各使用层、屋顶和室外图。
- 天沟须以屋面坡向、剖面和大样交叉辨认。跨楼层叠图先用同组轴网及第二个已知点核对平移和方向，再量取落管点；在系统图里复核每次转接的楼层。
- 改一处分支或引注后，重新检查关联的平面、系统、说明和图签。逐页 PDF、原生回读与建筑设计条件分别记录结果，已打印的页数只用于核对出图清单。

后台返回 succeeded 表示绘图任务已正常退出。verify 另核对实际管径与图层线型、原生对象范围、端点和指定连接。图纸的工程条件及纸面效果仍须按每个项目实际平面清单逐张验收。

本机两页校验试印基准可直接对照：[平面校验页](baseline/page0.pdf) · [系统校验页](baseline/page1.pdf)。两页使用固定母版和测试坐标，用于确认新机器的原生对象与打印表现。
