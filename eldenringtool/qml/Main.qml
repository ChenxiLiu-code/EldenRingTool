import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: win
    width: 1540
    height: 920
    minimumWidth: 1120
    minimumHeight: 700
    visible: true
    title: "EldenRingTool — 艾尔登法环全收集工具"
    color: "#0b0d11"

    palette.window: "#0b0d11"
    palette.windowText: "#edf0f4"
    palette.base: "#11161c"
    palette.text: "#edf0f4"
    palette.button: "#181d25"
    palette.buttonText: "#edf0f4"
    palette.highlight: "#c8a35f"
    palette.highlightedText: "#17140e"

    property color bg: "#0b0d11"
    property color bg2: "#0f1217"
    property color panel: "#13171d"
    property color panel2: "#181d25"
    property color panel3: "#1e242d"
    property color border: "#29313c"
    property color borderStrong: "#3a4452"
    property color gold: "#c8a35f"
    property color goldHi: "#dab875"
    property color goldDim: "#2a241a"
    property color textMain: "#edf0f4"
    property color muted: "#98a2b2"
    property color subtle: "#6e7888"
    property color success: "#79b887"
    property color danger: "#d06f76"
    property color warning: "#d4a45a"

    // Preserve delegates while changing only inserted, removed, moved or updated rows.
    function syncRows(model, rows, key) {
        var wanted = ({})
        for (var i = 0; i < rows.length; ++i) wanted[rows[i][key]] = true
        for (i = model.count - 1; i >= 0; --i)
            if (!wanted[model.get(i).payload[key]]) model.remove(i)
        for (i = 0; i < rows.length; ++i) {
            var at = i
            while (at < model.count && model.get(at).payload[key] !== rows[i][key]) ++at
            if (at === model.count) model.insert(i, {payload: rows[i]})
            else {
                if (at !== i) model.move(at, i, 1)
                if (JSON.stringify(model.get(i).payload) !== JSON.stringify(rows[i])) model.setProperty(i, "payload", rows[i])
            }
        }
    }

    component AppButton: Button {
        id: control
        property string tone: "secondary"
        property int contentAlignment: Text.AlignHCenter
        implicitHeight: 42
        implicitWidth: Math.max(78, buttonLabel.implicitWidth + 30)
        leftPadding: 15
        rightPadding: 15
        hoverEnabled: true
        font.pixelSize: 13
        font.weight: tone === "primary" ? Font.DemiBold : Font.Normal
        contentItem: Text {
            id: buttonLabel
            text: control.text
            font: control.font
            color: !control.enabled ? "#606976"
                  : control.tone === "primary" ? "#17140e"
                  : control.tone === "danger" ? "#efb3b7"
                  : control.highlighted ? "#e5cc9c"
                  : control.flat ? win.muted : win.textMain
            horizontalAlignment: control.contentAlignment
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 8
            color: !control.enabled ? "#11151a"
                 : control.tone === "primary" ? (control.down ? "#b68d46" : control.hovered ? win.goldHi : win.gold)
                 : control.tone === "danger" ? (control.hovered ? "#372126" : "#2a1b20")
                 : control.highlighted ? (control.hovered ? "#332b1d" : win.goldDim)
                 : control.flat ? (control.hovered ? win.panel2 : "transparent")
                 : (control.down ? "#222933" : control.hovered ? "#202630" : win.panel2)
            border.width: control.flat ? 0 : 1
            border.color: !control.enabled ? "#202630"
                        : control.tone === "primary" ? (control.hovered ? win.goldHi : win.gold)
                        : control.tone === "danger" ? "#66373d"
                        : control.highlighted ? "#675638"
                        : win.borderStrong
        }
    }

    component AppField: TextField {
        id: fieldControl
        implicitHeight: 44
        leftPadding: 12
        rightPadding: 12
        color: win.textMain
        placeholderTextColor: "#626c7a"
        selectionColor: win.gold
        selectedTextColor: "#17140e"
        font.pixelSize: 13
        background: Rectangle {
            radius: 8
            color: fieldControl.activeFocus ? "#11161c" : "#0f1318"
            border.width: 1
            border.color: fieldControl.activeFocus ? "#735f39" : win.border
        }
    }

    component AppCheckBox: CheckBox {
        id: checkControl
        spacing: 9
        font.pixelSize: 13
        indicator: Rectangle {
            implicitWidth: 18
            implicitHeight: 18
            x: checkControl.leftPadding
            y: (checkControl.height - height) / 2
            radius: 4
            color: checkControl.checked ? win.goldDim : "#11161c"
            border.width: 1
            border.color: checkControl.checked ? "#8a7144" : "#4a5562"
            Text {
                anchors.centerIn: parent
                visible: checkControl.checked
                text: "✓"
                color: win.goldHi
                font.pixelSize: 12
                font.bold: true
            }
        }
        contentItem: Text {
            text: checkControl.text
            font: checkControl.font
            color: checkControl.enabled ? win.textMain : win.subtle
            verticalAlignment: Text.AlignVCenter
            leftPadding: checkControl.indicator.width + checkControl.spacing
        }
    }

    component AppComboBox: ComboBox {
        id: comboControl
        implicitHeight: 44
        leftPadding: 12
        rightPadding: 32
        font.pixelSize: 13
        contentItem: Text {
            leftPadding: comboControl.leftPadding
            rightPadding: comboControl.rightPadding
            text: comboControl.displayText
            font: comboControl.font
            color: win.textMain
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            x: comboControl.width - width - 12
            y: (comboControl.height - height) / 2 - 1
            text: "⌄"
            color: win.subtle
            font.pixelSize: 15
        }
        background: Rectangle {
            radius: 8
            color: comboControl.pressed ? "#202630" : win.panel2
            border.width: 1
            border.color: comboControl.activeFocus ? "#735f39" : win.borderStrong
        }
        delegate: ItemDelegate {
            width: comboControl.width
            implicitHeight: 38
            contentItem: Text {
                text: comboControl.textRole && modelData && modelData[comboControl.textRole] !== undefined
                      ? modelData[comboControl.textRole] : modelData
                color: highlighted ? win.textMain : "#cfd5dd"
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                leftPadding: 10
            }
            background: Rectangle {
                radius: 6
                color: highlighted ? win.panel3 : "transparent"
            }
        }
        popup: Popup {
            y: comboControl.height + 5
            width: comboControl.width
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
            padding: 4
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: comboControl.popup.visible ? comboControl.delegateModel : null
                currentIndex: comboControl.highlightedIndex
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
            background: Rectangle {
                radius: 9
                color: "#151a21"
                border.width: 1
                border.color: win.borderStrong
            }
        }
    }

    component AppSwitch: Switch {
        id: switchControl
        implicitHeight: 32; implicitWidth: 130; spacing: 8
        indicator: Rectangle {
            x: 0; y: (parent.height - height) / 2
            width: 36; height: 20; radius: 10
            color: switchControl.checked ? "#397b62" : "#343c46"
            border.color: switchControl.activeFocus ? win.goldHi : "transparent"
            Rectangle {
                x: switchControl.checked ? 19 : 3; y: 3
                width: 14; height: 14; radius: 7
                color: switchControl.enabled ? "#edf4f0" : win.subtle
                Behavior on x { NumberAnimation { duration: 100 } }
            }
        }
        contentItem: Text {
            leftPadding: 44; text: switchControl.text
            verticalAlignment: Text.AlignVCenter
            color: switchControl.enabled ? win.textMain : win.subtle
            font.pixelSize: 12
        }
    }

    component AppTabButton: TabButton {
        id: tabControl
        implicitHeight: 38
        implicitWidth: 76
        hoverEnabled: true
        font.pixelSize: 13
        font.weight: checked ? Font.DemiBold : Font.Normal
        contentItem: Text {
            text: tabControl.text
            font: tabControl.font
            color: tabControl.checked ? win.textMain : tabControl.hovered ? "#cdd3dc" : win.muted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 7
            color: tabControl.checked ? win.panel2 : tabControl.hovered ? "#151a21" : "transparent"
            Rectangle {
                visible: tabControl.checked
                height: 2
                width: Math.min(34, parent.width - 18)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 3
                radius: 1
                color: win.gold
            }
        }
    }

    component AppProgressBar: ProgressBar {
        id: progressControl
        implicitHeight: 6
        background: Rectangle { radius: 3; color: "#202630" }
        contentItem: Item {
            implicitHeight: 6
            Rectangle {
                width: progressControl.visualPosition * parent.width
                height: parent.height
                radius: 3
                color: win.gold
            }
        }
    }

    component AppTextArea: TextArea {
        id: areaControl
        leftPadding: 12
        rightPadding: 12
        topPadding: 10
        bottomPadding: 10
        color: "#cfd5dd"
        selectionColor: win.gold
        selectedTextColor: "#17140e"
        background: Rectangle {
            radius: 9
            color: "#0d1116"
            border.width: 1
            border.color: win.border
        }
    }

    FileDialog {
        id: exeDialog
        title: "选择 Elden Ring 可执行文件"
        nameFilters: ["Elden Ring (eldenring.exe)", "Executable (*.exe)"]
        onAccepted: if (rootLoader.item && rootLoader.item.setGamePath) rootLoader.item.setGamePath(selectedFile)
    }
    FileDialog {
        id: saveDialog
        title: "选择只读存档"
        nameFilters: ["Elden Ring saves (*.sl2 *.co2 *.err)", "All files (*)"]
        onAccepted: backend.setSavePath(selectedFile)
    }
    FolderDialog {
        id: modDialog
        title: "可选：选择模组目录（含 regulation.bin）"
        onAccepted: if (rootLoader.item && rootLoader.item.setModPath) rootLoader.item.setModPath(selectedFolder)
    }

    Dialog {
        id: journeyResetDialog
        objectName: "journeyResetDialog"
        property var resetTarget: ({})
        title: "确认周目重置"
        modal: true
        anchors.centerIn: parent
        width: Math.min(460, win.width - 40)
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: win.panel; radius: 12; border.color: win.borderStrong }
        contentItem: Label {
            text: "清空角色「" + (journeyResetDialog.resetTarget.name || "") + "」（槽位 "
                + ((journeyResetDialog.resetTarget.slot || 0) + 1) + "）的全部手动地图标记和任务勾选？\n\n"
                + "此操作无法撤销。其他角色、游戏存档和自动识别进度不受影响。"
            wrapMode: Text.Wrap
            color: win.textMain
        }
        footer: DialogButtonBox {
            AppButton { objectName: "journeyResetCancel"; text: "取消"; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            AppButton { objectName: "journeyResetConfirm"; text: "确认清空"; DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole }
        }
        onAccepted: backend.resetCurrentManualMarks(resetTarget.scope || "")
    }

    Connections {
        target: backend
        function onScanLog(line) {
            if (rootLoader.item && rootLoader.item.appendLog) rootLoader.item.appendLog(line)
        }
        function onToast(message) {
            toastLabel.text = message
            toast.open()
        }
        function onDataChanged() {
            if (rootLoader.item && rootLoader.item.refreshData) rootLoader.item.refreshData()
        }
        function onMapChanged() { if (rootLoader.item && rootLoader.item.refreshMap) rootLoader.item.refreshMap() }
        function onCatalogChanged() { if (rootLoader.item && rootLoader.item.refreshCatalog) rootLoader.item.refreshCatalog() }
        function onQuestsChanged() { if (rootLoader.item && rootLoader.item.refreshQuests) rootLoader.item.refreshQuests() }
        function onContentPacksChanged() { if (rootLoader.item && rootLoader.item.refreshData) rootLoader.item.refreshData() }
    }

    Popup {
        id: toast
        x: (win.width - width) / 2
        y: win.height - height - 34
        padding: 14
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { radius: 8; color: "#2b303b"; border.color: win.border }
        contentItem: Label { id: toastLabel; color: "white" }
        Timer { interval: 2600; running: toast.visible; onTriggered: toast.close() }
    }

    Loader {
        id: rootLoader
        anchors.fill: parent
        sourceComponent: backend.setupRequired ? setupComponent : mainComponent
    }

    Component {
        id: setupComponent
        Rectangle {
            id: setupRoot
            color: win.bg

            function appendLog(line) {
                scanLog.text += (scanLog.text.length ? "\n" : "") + line
                scanLog.cursorPosition = scanLog.length
            }
            function setGamePath(path) { setupPath.text = path }
            function setModPath(path) { modPath.text = path }

            Rectangle {
                id: setupCard
                anchors.centerIn: parent
                width: Math.min(parent.width - 72, 900)
                height: Math.min(parent.height - 56, backend.scanRunning || scanLog.text.length ? 790 : 650)
                radius: 14
                color: win.panel
                border.width: 1
                border.color: win.border

                ScrollView {
                    id: setupScroll
                    anchors.fill: parent
                    anchors.margins: 1
                    leftPadding: 31
                    rightPadding: 31
                    topPadding: 30
                    bottomPadding: 1
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded

                    ColumnLayout {
                        width: setupScroll.availableWidth
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Item {
                                width: 23; height: 23
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 19; height: 19; radius: 10
                                    color: "transparent"
                                    border.width: 2
                                    border.color: win.gold
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 5; height: 5; radius: 3
                                    color: win.gold
                                }
                            }
                            Label {
                                text: "EldenRingTool"
                                font.pixelSize: 20
                                font.weight: Font.DemiBold
                                color: win.textMain
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitWidth: setupStatusRow.implicitWidth + 28
                                implicitHeight: 34
                                radius: 17
                                color: "#171b21"
                                border.width: 1
                                border.color: win.border
                                RowLayout {
                                    id: setupStatusRow
                                    anchors.centerIn: parent
                                    spacing: 8
                                    Rectangle { Layout.alignment: Qt.AlignVCenter; width: 7; height: 7; radius: 4; color: backend.scanRunning ? win.gold : win.warning }
                                    Label {
                                        id: setupStatus
                                        text: backend.scanRunning ? "正在解析" : "尚未解析"
                                        color: win.muted
                                        font.pixelSize: 11
                                    }
                                }
                            }
                        }

                        Label {
                            text: "游戏资源解析"
                            font.pixelSize: 28
                            font.weight: Font.DemiBold
                            color: win.textMain
                            Layout.topMargin: 22
                        }
                        Label {
                            text: backend.setupReason || "首次使用需要建立本地资源索引，完成后即可离线使用。"
                            color: win.muted
                            font.pixelSize: 13
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.topMargin: 5
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: setupInfo.implicitHeight + 26
                            Layout.topMargin: 24
                            radius: 10
                            color: "#10141a"
                            border.width: 1
                            border.color: win.border
                            Label {
                                id: setupInfo
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 13
                                text: "选择 eldenring.exe 后，工具会自动识别 Game 目录，检查解析依赖，并生成地图瓦片、标记、任务索引、图鉴和资源指纹。仅当所有必要资源完整验证后才进入主界面。"
                                wrapMode: Text.Wrap
                                lineHeight: 1.35
                                color: "#c8ced7"
                                font.pixelSize: 13
                            }
                        }

                        Rectangle {
                            visible: backend.missingDependencies.length > 0
                            Layout.fillWidth: true
                            Layout.preferredHeight: depWarning.implicitHeight + 26
                            Layout.topMargin: visible ? 14 : 0
                            radius: 10
                            color: "#272218"
                            border.width: 1
                            border.color: "#594a2e"
                            Label {
                                id: depWarning
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 13
                                text: "缺少解析依赖：" + backend.missingDependencies + "。开始解析后会在当前 Python 环境中自动安装，安装过程会显示在日志中。"
                                color: "#d9bd89"
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                                font.pixelSize: 12
                            }
                        }

                        Label {
                            text: "ELDEN RING 可执行文件"
                            color: win.muted
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            Layout.topMargin: 22
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 7
                            spacing: 10
                            AppField {
                                id: setupPath
                                Layout.fillWidth: true
                                placeholderText: "…/ELDEN RING/Game/eldenring.exe"
                                text: backend.gameDir ? backend.gameDir + "/eldenring.exe" : ""
                            }
                            AppButton {
                                text: "浏览…"
                                Layout.preferredWidth: 94
                                onClicked: exeDialog.open()
                            }
                        }
                        Label {
                            text: "工具只读游戏文件，不会修改游戏目录。"
                            color: win.subtle
                            font.pixelSize: 11
                            Layout.topMargin: 6
                        }

                        Label {
                            text: "模组目录  ·  可选"
                            color: win.muted
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            Layout.topMargin: 18
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 7
                            spacing: 10
                            AppField {
                                id: modPath
                                Layout.fillWidth: true
                                placeholderText: "留空表示使用原版资源"
                            }
                            AppButton {
                                text: "选择…"
                                Layout.preferredWidth: 94
                                onClicked: modDialog.open()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 24
                            spacing: 10
                            AppButton {
                                text: backend.scanRunning ? "正在解析…" : "开始解析"
                                tone: "primary"
                                Layout.preferredWidth: 128
                                enabled: !backend.scanRunning && setupPath.text.length > 0
                                onClicked: {
                                    scanLog.text = ""
                                    backend.startScan(setupPath.text, modPath.text)
                                }
                            }
                            AppButton {
                                text: "取消"
                                visible: backend.scanRunning
                                tone: "danger"
                                onClicked: backend.cancelScan()
                            }
                            AppButton {
                                text: "重新检查现有缓存"
                                flat: true
                                visible: backend.gameDir.length > 0 && !backend.scanRunning
                                onClicked: backend.keepCurrentCache()
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitWidth: resourceBadge.implicitWidth + 22
                                implicitHeight: 27
                                radius: 14
                                color: "#161b22"
                                border.width: 1
                                border.color: win.border
                                Label {
                                    id: resourceBadge
                                    anchors.centerIn: parent
                                    text: "资源校验 · SHA-256"
                                    color: win.subtle
                                    font.pixelSize: 11
                                }
                            }
                        }

                        AppProgressBar {
                            Layout.fillWidth: true
                            Layout.topMargin: 16
                            visible: backend.scanRunning
                            value: backend.scanProgress
                        }
                        Label {
                            text: backend.scanStatus
                            visible: backend.scanRunning
                            color: win.goldHi
                            font.pixelSize: 12
                            Layout.topMargin: visible ? 8 : 0
                        }

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: backend.scanRunning || scanLog.text.length ? 210 : 0
                            Layout.topMargin: visible ? 10 : 0
                            visible: backend.scanRunning || scanLog.text.length > 0
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                            ScrollBar.vertical.policy: ScrollBar.AsNeeded
                            AppTextArea {
                                id: scanLog
                                readOnly: true
                                wrapMode: TextEdit.NoWrap
                                font.family: "Consolas"
                                font.pixelSize: 11
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: win.border
                            Layout.topMargin: 22
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 15
                            Layout.bottomMargin: 28
                            spacing: 20
                            Label {
                                Layout.fillWidth: true
                                text: "解析失败、取消或过程中检测到资源变化时，不会写入“解析成功”记录。"
                                color: win.subtle
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                            Label {
                                text: "游戏资源 / .sl2 存档均只读"
                                color: win.subtle
                                font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: mainComponent
        Rectangle {
            id: mainRoot
            property var categories: backend.categoryList()
            color: win.bg

            function refreshData() {
                Qt.callLater(applyRefresh)
            }
            function applyRefresh() {
                categories = backend.categoryList()
                if (!backend.masterVisible(mapPage.master)) mapPage.master = "M00"
                mapPage.refreshViewport()
                questPage.refresh()
                catalogPage.refresh()
            }
            function refreshMap() { mapPage.refreshViewport() }
            function refreshCatalog() { catalogPage.refresh() }
            function refreshQuests() { questPage.refresh() }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 64
                    color: "#0e1116"
                    border.width: 1
                    border.color: win.border

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 12

                        Item {
                            width: 22; height: 22
                            Rectangle {
                                anchors.centerIn: parent
                                width: 18; height: 18; radius: 9
                                color: "transparent"
                                border.width: 2
                                border.color: win.gold
                            }
                            Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: win.gold }
                        }
                        Label {
                            text: "EldenRingTool"
                            color: win.textMain
                            font.pixelSize: 19
                            font.weight: Font.DemiBold
                        }

                        TabBar {
                            id: mainNav
        objectName: "mainNav"
                            Layout.leftMargin: 8
                            Layout.preferredWidth: 350
                            Layout.preferredHeight: 42
                            padding: 3
                            spacing: 2
                            background: Rectangle {
                                radius: 10
                                color: "#11151b"
                                border.width: 1
                                border.color: win.border
                            }
                            AppTabButton { text: "地图" }
                            AppTabButton { text: "任务" }
                            AppTabButton { text: "图鉴" }
                            AppTabButton { text: "设置" }
                        }

                        Item { Layout.fillWidth: true }
                        Rectangle { width: 1; Layout.preferredHeight: 32; color: win.border }
                        ColumnLayout {
                            spacing: 1
                            Label {
                                text: backend.activeCharacter.name || "未检测到存档角色"
                                color: backend.activeCharacter.name ? win.textMain : win.muted
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: {
                                    var c = backend.activeCharacter, p = c.position
                                    if (!p) return "位置 / 高度：等待存档"
                                    var h = c.mapPixel ? c.mapPixel.h : null
                                    return p.mapId + " · X " + Number(p.x).toFixed(1) + " / Z " + Number(p.z).toFixed(1) +
                                        " · " + (h === null ? "局部高度 " + Number(p.y).toFixed(1) : "绝对高度 " + h) + " m"
                                }
                                color: win.subtle
                                font.pixelSize: 10
                            }
                        }
                        AppComboBox {
                            visible: backend.characterList.length > 1
                            Layout.preferredWidth: 166
                            Layout.preferredHeight: 38
                            model: backend.characterList
                            textRole: "name"
                            currentIndex: Math.max(0, backend.characterList.findIndex(function(x) { return x.slot === backend.activeSlot }))
                            onActivated: if (currentIndex >= 0) backend.setActiveSlot(backend.characterList[currentIndex].slot)
                        }
                        AppButton {
                            text: "刷新存档"
                            flat: true
                            Layout.preferredHeight: 36
                            onClicked: backend.refresh_save(true)
                        }
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: mainNav.currentIndex

                    RowLayout {
                        spacing: 0
                        Rectangle {
                            Layout.preferredWidth: 270
                            Layout.fillHeight: true
                            color: win.panel
                            border.width: 1
                            border.color: win.border

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 10
                                Label {
                                    text: "地图筛选"
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    color: win.textMain
                                }
                                AppField {
                                    Layout.fillWidth: true
                                    placeholderText: "搜索标记…"
                                    onTextChanged: { mapPage.searchText = text; mapPage.refreshViewport() }
                                }
                                AppCheckBox {
                                    text: "隐藏已完成"
                                    checked: backend.displaySettings.mapHideCompleted
                                    enabled: backend.activeSlot >= 0
                                    onToggled: backend.setDisplaySetting("mapHideCompleted", checked)
                                }
                                Rectangle { Layout.fillWidth: true; height: 1; color: win.border }
                                Label {
                                    text: "类别"
                                    color: win.subtle
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                                ScrollView {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                    Column {
                                        width: parent.width
                                        spacing: 3
                                        AppButton {
                                            width: parent.width
                                            text: "全部类别"
                                            flat: mapPage.categoryFilter !== ""
                                            highlighted: mapPage.categoryFilter === ""
                                            contentAlignment: Text.AlignLeft
                                            onClicked: { mapPage.categoryFilter = ""; mapPage.refreshViewport() }
                                        }
                                        Repeater {
                                            model: mainRoot.categories
                                            delegate: AppCheckBox {
                                                required property var modelData
                                                width: parent.width
                                                text: modelData.name + "   " + modelData.count
                                                checked: mapPage.categoryFilter === "" || mapPage.categoryFilter.split(",").indexOf(modelData.id) >= 0
                                                onToggled: {
                                                    var cats = mapPage.categoryFilter === "" ? mainRoot.categories.map(function(c) { return c.id }) : mapPage.categoryFilter.split(",")
                                                    cats = cats.filter(function(c) { return c !== modelData.id && c !== "__none__" })
                                                    if (checked) cats.push(modelData.id)
                                                    mapPage.categoryFilter = cats.length ? cats.join(",") : "__none__"
                                                    mapPage.refreshViewport()
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        MapPage { id: mapPage; Layout.fillWidth: true; Layout.fillHeight: true }
                    }

                    QuestPage {
                        id: questPage
                        onLocateRequested: function(markerId) {
                            mainNav.currentIndex = 0
                            Qt.callLater(function() { mapPage.locate(markerId) })
                        }
                    }
                    CatalogPage { id: catalogPage; onLocateRequested: function(markerId) { mainNav.currentIndex = 0; Qt.callLater(function() { mapPage.locate(markerId) }) } }
                    SettingsPage { id: settingsPage }
                }
            }

            Component.onCompleted: {
                questPage.refresh()
                catalogPage.refresh()
            }
        }
    }

    component MapPage: Rectangle {
        id: mapRoot
        objectName: "mapRoot"
        color: "#0d1014"
        clip: true
        property string master: "M00"
        property real mapZoom: 0.12
        property real renderZoom: 0.12
        property bool inMotion: mapDrag.active || zoomAnimation.running || panX.running || panY.running
        onInMotionChanged: if (!inMotion) refreshDelay.restart()
        property string categoryFilter: ""
        property string searchText: ""
        property bool hideCompleted: backend.displaySettings.mapHideCompleted
        onHideCompletedChanged: refreshDelay.restart()
        property var playerPosition: backend.activeCharacter.mapPixel || null
        property alias tileModel: tiles
        property alias markerModel: markers
        property var baseModel: []
        ListModel { id: tiles; dynamicRoles: true }
        ListModel { id: markers }
        property var requestedTiles: []
        property var displayedTileSources: ({})
        property bool tilesPending: false
        function stageTiles(rows) {
            requestedTiles = rows
            tilesPending = true
            // Retain the displayed mip until every replacement image is ready.
            var retained = [], seen = ({})
            for (var i = 0; i < rows.length; ++i) seen[rows[i].source] = true
            for (i = 0; i < tiles.count; ++i) {
                var row = tiles.get(i).payload
                if (!seen[row.source] && displayedTileSources[row.source])
                    retained.push({source: row.source, x: row.x, y: row.y, size: row.size})
            }
            reconcile(tiles, rows.concat(retained), "source")
            Qt.callLater(commitTiles)
        }
        function commitTiles() {
            if (!tilesPending) return
            var ready = ({})
            for (var i = 0; i < tileRepeater.count; ++i) {
                var tile = tileRepeater.itemAt(i)
                if (tile && (tile.status === Image.Ready || tile.status === Image.Error))
                    ready[tile.modelData.source] = true
            }
            var next = ({})
            for (i = 0; i < requestedTiles.length; ++i) {
                var source = requestedTiles[i].source
                if (!ready[source]) return
                next[source] = true
            }
            tilesPending = false
            displayedTileSources = next
            reconcile(tiles, requestedTiles, "source")
        }
        property var rowSignatures: ({})
        function reconcile(model, rows, key) {
            var signatures = rowSignatures[key] || ({})
            var nextSignatures = ({})
            var wanted = ({})
            for (var j = 0; j < rows.length; ++j) wanted[rows[j][key]] = true
            for (var i = model.count - 1; i >= 0; --i)
                if (!wanted[model.get(i).payload[key]]) model.remove(i)
            var existing = ({})
            for (i = 0; i < model.count; ++i) existing[model.get(i).payload[key]] = i
            for (j = 0; j < rows.length; ++j) {
                var row = rows[j], at = existing[row[key]]
                var signature = JSON.stringify(row)
                nextSignatures[row[key]] = signature
                if (at === undefined) model.append({payload: row})
                else if (signatures[row[key]] !== signature) model.setProperty(at, "payload", row)
            }
            rowSignatures[key] = nextSignatures
        }
        onMasterChanged: {
            stopMotion()
            tilesPending = false
            requestedTiles = []
            displayedTileSources = ({})
            tiles.clear(); markers.clear()
            baseModel = backend.baseTiles(master)
            refreshDelay.restart()
        }
        property string selectedMarker: ""
        property bool initialized: false
        property real zoomAnchorX: 0
        property real zoomAnchorY: 0
        property real zoomScreenX: 0
        property real zoomScreenY: 0
        onMapZoomChanged: {
            if (zoomAnimation.running) {
                flick.contentX = zoomAnchorX * mapZoom - zoomScreenX
                flick.contentY = zoomAnchorY * mapZoom - zoomScreenY
            }
            if (!inMotion) refreshDelay.restart()
        }
        NumberAnimation { id: zoomAnimation; target: mapRoot; property: "mapZoom"; duration: 180; easing.type: Easing.OutCubic }
        function stopMotion() {
            zoomAnimation.stop()
            panX.stop(); panY.stop()
        }
        function animateZoom(factor, sx, sy) {
            var targetZoom = Math.max(0.04, Math.min(2.8, (zoomAnimation.running ? zoomAnimation.to : mapZoom) * factor))
            stopMotion()
            zoomAnchorX = (flick.contentX + sx) / mapZoom
            zoomAnchorY = (flick.contentY + sy) / mapZoom
            zoomScreenX = sx; zoomScreenY = sy
            zoomAnimation.from = mapZoom; zoomAnimation.to = targetZoom
            zoomAnimation.start()
        }

        function refreshViewport() {
            if (!backend.masterVisible(master)) { master = "M00"; return }
            if (markerPopup.opened) {
                var detail = backend.markerDetails(selectedMarker)
                if (detail.id) markerPopup.d = detail
                else markerPopup.close()
            }
            if (!visible || !flick.width || backend.setupRequired || inMotion) return
            renderZoom = mapZoom
            var left = flick.contentX / mapZoom
            var top = flick.contentY / mapZoom
            var right = (flick.contentX + flick.width) / mapZoom
            var bottom = (flick.contentY + flick.height) / mapZoom
            var margin = 240 / mapZoom
            left -= margin; top -= margin; right += margin; bottom += margin
            stageTiles(backend.visibleTiles(master, mapZoom, left, top, right, bottom))
            reconcile(markers, backend.visibleMarkers(master, mapZoom, left, top, right, bottom, searchText, categoryFilter, hideCompleted), "id")
        }
        function fitMap() {
            stopMotion()
            var z = Math.min(width / backend.masterPx, height / backend.masterPx) * 0.96
            mapZoom = Math.max(0.045, z)
            flick.contentX = (backend.masterPx * mapZoom - width) / 2
            flick.contentY = (backend.masterPx * mapZoom - height) / 2
            refreshViewport()
        }
        function centerAt(x, y, zoomValue) {
            stopMotion()
            mapZoom = Math.max(0.04, Math.min(2.8, zoomValue))
            flick.contentX = x * mapZoom - flick.width / 2
            flick.contentY = y * mapZoom - flick.height / 2
            refreshDelay.restart()
        }
        function zoomBy(factor) {
            animateZoom(factor, flick.width / 2, flick.height / 2)
        }
        function locate(id) {
            var d = backend.markerDetails(id)
            if (d.px === undefined || d.px === null) return
            master = d.master
            selectedMarker = id
            centerAt(d.px, d.py, Math.max(mapZoom, 0.7))
        }
        function locatePlayer() {
            if (!playerPosition || !backend.masterVisible(playerPosition.master)) return
            master = playerPosition.master
            centerAt(playerPosition.px, playerPosition.py, Math.max(mapZoom, 0.7))
        }

        Component.onCompleted: { baseModel = backend.baseTiles(master); Qt.callLater(fitMap) }
        onVisibleChanged: { stopMotion(); if (visible) refreshDelay.restart() }
        onWidthChanged: if (!initialized && width > 300) { initialized = true; Qt.callLater(fitMap) }

        Item {
            id: flick
        objectName: "mapViewport"
            property real contentX: 0
            property real contentY: 0
            anchors.fill: parent
            clip: true
            onContentXChanged: if (!mapRoot.inMotion) refreshDelay.restart()
            onContentYChanged: if (!mapRoot.inMotion) refreshDelay.restart()

            NumberAnimation { id: panX; target: flick; property: "contentX"; duration: 420; easing.type: Easing.OutCubic }
            NumberAnimation { id: panY; target: flick; property: "contentY"; duration: 420; easing.type: Easing.OutCubic }
            PointHandler {
                acceptedButtons: Qt.LeftButton
                onActiveChanged: if (active) mapRoot.stopMotion()
            }

            DragHandler {
                id: mapDrag
                target: null
                acceptedButtons: Qt.LeftButton
                property point previous: Qt.point(0, 0)
                property point velocity: Qt.point(0, 0)
                onActiveChanged: {
                    if (active) {
                        mapRoot.stopMotion()
                        previous = Qt.point(0, 0)
                        velocity = Qt.point(0, 0)
                    } else {
                        panX.from = flick.contentX; panX.to = flick.contentX - Math.max(-2200, Math.min(2200, velocity.x)) * 0.14
                        panY.from = flick.contentY; panY.to = flick.contentY - Math.max(-2200, Math.min(2200, velocity.y)) * 0.14
                        panX.start(); panY.start()
                    }
                }
                onActiveTranslationChanged: {
                    if (!active) return
                    flick.contentX -= activeTranslation.x - previous.x
                    flick.contentY -= activeTranslation.y - previous.y
                    previous = activeTranslation
                    velocity = centroid.velocity
                }
            }
            Item {
                x: -flick.contentX; y: -flick.contentY
                width: backend.masterPx * mapRoot.renderZoom
                height: backend.masterPx * mapRoot.renderZoom
                transformOrigin: Item.TopLeft
                scale: mapRoot.mapZoom / mapRoot.renderZoom
                Rectangle {
                    objectName: "playerMarker"
                    visible: !!mapRoot.playerPosition && mapRoot.playerPosition.master === mapRoot.master
                    x: (mapRoot.playerPosition ? mapRoot.playerPosition.px : 0) * mapRoot.renderZoom - width / 2
                    y: (mapRoot.playerPosition ? mapRoot.playerPosition.py : 0) * mapRoot.renderZoom - height / 2
                    width: 20; height: 20; radius: 10
                    z: 15
                    color: "#168da1"; border.color: "white"; border.width: 3
                    Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: "white" }
                    MouseArea {
                        id: playerHover
                        anchors.fill: parent
                        hoverEnabled: true
                    }
                    ToolTip.visible: playerHover.containsMouse
                    ToolTip.text: (backend.activeCharacter.name || "角色") + " · 最近存档位置"
                }
                Repeater {
                    model: mapRoot.baseModel
                    delegate: Image {
                        required property var modelData
                        x: modelData.x * mapRoot.renderZoom; y: modelData.y * mapRoot.renderZoom
                        width: modelData.size * mapRoot.renderZoom + 1; height: width
                        source: modelData.source; asynchronous: true; cache: true; smooth: true
                    }
                }
                Repeater {
                    id: tileRepeater
                    model: mapRoot.tileModel
                    delegate: Image {
                        objectName: "mapTile"
                        required property var payload
                        property var modelData: payload
                        visible: !!mapRoot.displayedTileSources[modelData.source]
                        onStatusChanged: Qt.callLater(mapRoot.commitTiles)
                        x: modelData.x * mapRoot.renderZoom
                        y: modelData.y * mapRoot.renderZoom
                        width: modelData.size * mapRoot.renderZoom + 1
                        height: modelData.size * mapRoot.renderZoom + 1
                        source: modelData.source
                        fillMode: Image.Stretch
                        smooth: true
                        asynchronous: true
                        cache: true
                    }
                }
                Repeater {
                    model: mapRoot.markerModel
                    delegate: Item {
                        required property var payload
                        property var modelData: payload
                        x: modelData.x * mapRoot.renderZoom - width / 2
                        y: modelData.y * mapRoot.renderZoom - height / 2
                        width: modelData.found ? 10 : modelData.cluster ? 38 : (modelData.cat === "boss" ? 12 : Math.max(20, Math.min(28, 24 * mapRoot.renderZoom)))
                        height: width
                        z: modelData.cat === "boss" ? 10 : 5
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width
                            height: width
                            radius: width / 2
                            color: modelData.found ? "#58bd87" : modelData.cluster ? "#252b34" : (modelData.cat === "boss" ? "#e44550" : win.gold)
                            opacity: modelData.found ? 0.5 : 1
                            border.color: modelData.cluster ? "#596474" : "#0d0f12"
                            border.width: 1
                        }
                        Image {
                            visible: !modelData.found && !modelData.cluster && modelData.cat !== "boss"
                            anchors.centerIn: parent
                            width: parent.width * 0.88
                            height: width
                            source: visible && modelData.icon ? backend.assetsRoot + "icons/" + modelData.icon : ""
                            asynchronous: true
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }
                        Label {
                            visible: modelData.cluster && !modelData.found
                            anchors.centerIn: parent
                            text: modelData.count
                            font.bold: true
                            color: "white"
                            font.pixelSize: 12
                        }
                        Label {
                            visible: modelData.cat === "boss" && !modelData.found
                            anchors.top: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.name; color: "#ff6973"; font.pixelSize: 12; font.bold: true
                            style: Text.Outline; styleColor: "#140508"
                        }
                        MouseArea {
                            id: markerMouse
                            anchors.fill: parent
                            anchors.margins: modelData.cat === "boss" ? -5 : 0
                            hoverEnabled: true
                            onClicked: {
                                if (modelData.cluster) {
                                    mapRoot.centerAt(modelData.x, modelData.y, Math.min(2.8, mapRoot.mapZoom * 1.9))
                                } else {
                                    mapRoot.selectedMarker = modelData.id
                                    markerPopup.open()
                                }
                            }
                            ToolTip {
                                id: markerTip
                                visible: markerMouse.containsMouse && !mapRoot.inMotion
                                delay: 350
                                x: markerMouse.mouseX + 10
                                y: markerMouse.mouseY + 10
                                text: modelData.cluster ? modelData.name : modelData.name + "\n绝对高度：" + (modelData.h === null || modelData.h === undefined ? "未知" : modelData.h + " m")
                                background: Rectangle { radius: 7; color: "#151a21"; border.width: 1; border.color: win.borderStrong }
                                contentItem: Text {
                                    text: markerTip.text
                                    color: win.textMain
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }

            WheelHandler {
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                target: null
                onWheel: function(event) {
                    event.accepted = true
                    var delta = event.pixelDelta.y !== 0 ? event.pixelDelta.y * 2 : event.angleDelta.y
                    if (delta !== 0) mapRoot.animateZoom(Math.pow(1.18, delta / 120), event.x, event.y)
                }
            }
        }

        Timer { id: refreshDelay; interval: 80; repeat: false; onTriggered: mapRoot.refreshViewport() }

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.topMargin: 14
            anchors.leftMargin: 14
            height: 46
            width: masterTabs.implicitWidth + 10
            radius: 10
            color: "#e60d1015"
            border.width: 1
            border.color: win.border
            z: 20
            Row {
                id: masterTabs
                anchors.centerIn: parent
                spacing: 4
                Repeater {
                    model: [{id: "M00", name: "交界地"}, {id: "M01", name: "地下"}, {id: "M10", name: "幽影之地"}, {id: "M11", name: "幽影地下"}]
                    delegate: AppButton {
                        required property var modelData
                        height: 36
                        text: modelData.name
                        flat: mapRoot.master !== modelData.id
                        visible: backend.contentPacks.dlc !== "hide" || (modelData.id !== "M10" && modelData.id !== "M11")
                        highlighted: mapRoot.master === modelData.id
                        onClicked: { mapRoot.master = modelData.id; mapRoot.refreshViewport() }
                    }
                }
            }
        }

        Column {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 14
            anchors.rightMargin: 14
            spacing: 6
            z: 20
            AppButton { width: 38; height: 38; text: "+"; onClicked: mapRoot.zoomBy(1.22) }
            AppButton { width: 38; height: 38; text: "−"; onClicked: mapRoot.zoomBy(1 / 1.22) }
            AppButton {
                objectName: "fitMapButton"
                width: 38; height: 38; text: "⛶"
                onClicked: mapRoot.fitMap()
                ToolTip.visible: hovered
                ToolTip.text: "适配地图"
            }
            AppButton {
                objectName: "locatePlayerButton"
                width: 38; height: 38; text: "⌖"
                enabled: !!mapRoot.playerPosition
                onClicked: mapRoot.locatePlayer()
                ToolTip.visible: hovered
                ToolTip.text: enabled ? "定位角色（最近存档位置）" : "暂无可用的角色位置"
            }
        }

        Rectangle {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: 14
            anchors.bottomMargin: 14
            implicitWidth: mapStatus.implicitWidth + 20
            implicitHeight: 30
            radius: 8
            color: "#df0d1015"
            border.width: 1
            border.color: win.border
            z: 20
            Label {
                id: mapStatus
                anchors.centerIn: parent
                text: "缩放 " + Math.round(mapRoot.mapZoom * 100) + "% · 当前视野 " + mapRoot.markerModel.count + " 个标记 · 瓦片 " + mapRoot.tileModel.count
                color: win.subtle
                font.pixelSize: 10
            }
        }

        Popup {
            id: markerPopup
            x: Math.max(12, (mapRoot.width - width) / 2)
            y: 70
            width: Math.min(460, mapRoot.width - 24)
            padding: 16
            modal: false
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
            property var d: ({})
            onOpened: d = backend.markerDetails(mapRoot.selectedMarker)
            background: Rectangle { color: "#171c23"; radius: 12; border.width: 1; border.color: win.borderStrong }
            contentItem: ColumnLayout {
                spacing: 8
                Label { text: markerPopup.d.name || ""; font.pixelSize: 19; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { text: markerPopup.d.catName || markerPopup.d.cat || ""; color: win.gold }
                Label { text: "绝对高度：" + (markerPopup.d.h === undefined || markerPopup.d.h === null ? "未知（源数据未提供高度）" : markerPopup.d.h + " m"); color: win.textMain }
                Label { visible: !!markerPopup.d.tip; text: markerPopup.d.tip || ""; wrapMode: Text.Wrap; Layout.fillWidth: true }
                AppCheckBox {
                    text: "当前角色：手动标记为已收集"
                    checked: !!markerPopup.d.manual
                    enabled: backend.activeSlot >= 0 && !(markerPopup.d.found && !markerPopup.d.manual)
                    onToggled: {
                        backend.setMarkerChecked(mapRoot.selectedMarker, checked)
                        markerPopup.d = backend.markerDetails(mapRoot.selectedMarker)
                        mapRoot.refreshViewport()
                    }
                }
            }
        }
    }

    component QuestPage: Rectangle {
        id: questRoot
        objectName: "questRoot"
        color: win.bg2
        signal locateRequested(string markerId)
        property string packFilter: "all"
        property string statusFilter: "all"
        property var questModel: []
        ListModel { id: questRows; dynamicRoles: true }
        property int selectedIndex: -1
        property string stepFilter: "all"
        property var currentQuest: selectedIndex >= 0 && selectedIndex < questModel.length ? questModel[selectedIndex] : ({})
        property bool refreshPending: true
        onVisibleChanged: if (visible && refreshPending) refresh()

        function refresh() {
            refreshPending = true
            if (visible) questRefresh.restart()
        }
        Timer { id: questRefresh; interval: 100; onTriggered: questRoot.applyRefresh() }
        function applyRefresh() {
            if (!visible) return
            refreshPending = false
            var oldId = currentQuest.id || ""
            if (backend.contentPacks[packFilter] === "hide") packFilter = "all"
            var rows = backend.questCards(statusFilter, questSearch.text, packFilter)
            win.syncRows(questRows, rows, "id")
            if (JSON.stringify(questModel) !== JSON.stringify(rows)) questModel = rows
            var found = -1
            for (var i = 0; i < questModel.length; ++i) {
                if (questModel[i].id === oldId) { found = i; break }
            }
            selectedIndex = found >= 0 ? found : (questModel.length ? 0 : -1)
            if (oldId !== (currentQuest.id || "")) questDetailScroll.contentItem.contentY = 0
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.topMargin: 18
            anchors.bottomMargin: 18
            spacing: 13

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 2
                    Label { text: "任务指引"; font.pixelSize: 23; font.weight: Font.DemiBold; color: win.textMain }
                    Label { text: "根据当前存档状态整理可进行步骤、风险节点与分支。"; color: win.muted; font.pixelSize: 11 }
                }
                Item { Layout.fillWidth: true }
                Label { text: questRoot.questModel.length + " 条任务"; color: win.subtle; font.pixelSize: 11 }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 9
                AppField {
                    id: questSearch
                    Layout.fillWidth: true
                    Layout.maximumWidth: 520
                    placeholderText: "搜索任务、角色、地点或奖励…"
                    onTextChanged: questRoot.refresh()
                }
                Item { Layout.fillWidth: true }
            }

            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Repeater {
                    model: [{id:"all", name:"全部内容"}, {id:"base", name:"本体"}, {id:"dlc", name:"黄金树幽影"}, {id:"tarnished", name:"褪色者礼包"}]
                    delegate: AppButton {
                        required property var modelData
                        Layout.preferredWidth: 130; Layout.preferredHeight: 36
                        text: modelData.name; highlighted: questRoot.packFilter === modelData.id
                        visible: backend.contentPacks[modelData.id] !== "hide"
                        onClicked: { questRoot.packFilter = modelData.id; questRoot.refresh() }
                    }
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 6
                Repeater {
                    model: [{id:"todo",name:"待办"},{id:"active",name:"进行中"},{id:"available",name:"可接受"},{id:"risk",name:"风险"},{id:"all",name:"全部"},{id:"completed",name:"已完成"},{id:"locked",name:"未解锁"},{id:"failed",name:"已失败"}]
                    delegate: AppButton {
                        required property var modelData
                        text: modelData.name; highlighted: questRoot.statusFilter === modelData.id
                        onClicked: { questRoot.statusFilter = modelData.id; questRoot.refresh() }
                    }
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                Rectangle {
                    Layout.preferredWidth: 310
                    Layout.fillHeight: true
                    color: win.panel
                    radius: 12
                    border.width: 1
                    border.color: win.border

                    ListView {
                        id: questList
                        anchors.fill: parent
                        anchors.margins: 8
                        clip: true
                        spacing: 5
                        model: questRows
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            required property var payload
                            property var modelData: payload
                            required property int index
                            width: ListView.view.width
                            height: 96
                            radius: 8
                            color: index === questRoot.selectedIndex ? "#211f1b" : win.panel2
                            border.width: 1
                            border.color: index === questRoot.selectedIndex ? "#625336" : "transparent"

                            Rectangle {
                                visible: index === questRoot.selectedIndex
                                x: 0
                                y: 12
                                width: 3
                                height: parent.height - 24
                                radius: 2
                                color: win.gold
                            }

                            Column {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 10
                                anchors.topMargin: 10
                                anchors.bottomMargin: 8
                                spacing: 5
                                Row {
                                    width: parent.width
                                    Label {
                                        width: parent.width - 68
                                        text: modelData.name
                                        elide: Text.ElideRight
                                        color: win.textMain
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                    }
                                    Label {
                                        width: 68
                                        horizontalAlignment: Text.AlignRight
                                        text: modelData.progress
                                        color: win.goldHi
                                        font.pixelSize: 11
                                    }
                                }
                                Row {
                                    spacing: 10
                                    Label {
                                        text: ({failed:"已失败",completed:"已完成",active:"进行中",available:"可接受",locked:"未解锁"})[modelData.status] || modelData.status
                                        color: modelData.status === "failed" ? win.danger
                                             : modelData.status === "completed" ? win.success
                                             : modelData.status === "active" ? win.goldHi : win.muted
                                        font.pixelSize: 11
                                    }
                                    Label {
                                        text: modelData.character
                                        width: 170
                                        color: win.subtle
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                            Label {
                                x: 12; y: 66; width: parent.width - 24; elide: Text.ElideRight
                                text: modelData.nextAction ? "下一步 · " + modelData.nextAction : "暂无待办步骤"
                                font.pixelSize: 11; color: win.muted
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    if (questRoot.selectedIndex !== index) questDetailScroll.contentItem.contentY = 0
                                    questRoot.selectedIndex = index
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: win.panel
                    radius: 12
                    border.width: 1
                    border.color: win.border

                    ScrollView {
                        id: questDetailScroll
                        anchors.fill: parent
                        anchors.leftMargin: 20
                        anchors.rightMargin: 16
                        anchors.topMargin: 18
                        anchors.bottomMargin: 18
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        Column {
                            width: questDetailScroll.availableWidth
                            spacing: 10

                            Label {
                                width: parent.width
                                text: questRoot.currentQuest.name || "选择左侧任务"
                                font.pixelSize: 23
                                font.weight: Font.DemiBold
                                color: win.textMain
                                wrapMode: Text.Wrap
                            }
                            Label {
                                visible: text.length > 0
                                width: parent.width
                                text: questRoot.currentQuest.character || ""
                                color: win.muted
                                font.pixelSize: 11
                            }
                            Rectangle {
                                visible: (questRoot.currentQuest.risks || []).length > 0
                                width: parent.width
                                height: 1
                                color: win.border
                            }

                            Repeater {
                                model: questRoot.currentQuest.risks || []
                                delegate: Rectangle {
                                    required property var modelData
                                    width: parent.width
                                    height: riskText.implicitHeight + 24
                                    radius: 9
                                    color: modelData.triggered ? "#2b1b1f" : "#272218"
                                    border.width: 1
                                    border.color: modelData.triggered ? "#65373c" : "#594a2e"
                                    Label {
                                        id: riskText
                                        x: 12
                                        y: 12
                                        width: parent.width - 24
                                        text: (modelData.triggered ? "已触发：" : "注意：") + (modelData.text || modelData.id)
                                        wrapMode: Text.Wrap
                                        lineHeight: 1.3
                                        color: modelData.triggered ? "#e8a7ab" : "#d9bd89"
                                        font.pixelSize: 12
                                    }
                                }
                            }

                            Label {
                                width: parent.width; wrapMode: Text.Wrap
                                visible: !!questRoot.currentQuest.id
                                text: "已完成 " + (questRoot.currentQuest.doneCount || 0) + " / " + (questRoot.currentQuest.stepCount || 0) + " 步"
                                color: win.success; font.pixelSize: 12
                            }
                            Flow {
                                width: parent.width; spacing: 6
                                Repeater {
                                    model: [{id:"all",name:"全部步骤"},{id:"todo",name:"待办步骤"},{id:"available",name:"可进行"}]
                                    delegate: AppButton {
                                        required property var modelData
                                        text: modelData.name; highlighted: questRoot.stepFilter === modelData.id
                                        onClicked: questRoot.stepFilter = modelData.id
                                    }
                                }
                            }
                            Repeater {
                                model: (questRoot.currentQuest.steps || []).filter(function(s) {
                                    return questRoot.stepFilter === "all" || (questRoot.stepFilter === "available" ? s.state === "available" : !s.complete && s.state !== "missed" && s.state !== "superseded")
                                })
                                delegate: Rectangle {
                                    required property var modelData
                                    width: parent.width
                                    height: stepColumn.implicitHeight + 24
                                    radius: 9
                                    color: modelData.state === "available" ? "#14251f" : "#10141a"
                                    border.width: 1
                                    border.color: modelData.state === "available" ? "#386853" : win.border

                                    Column {
                                        id: stepColumn
                                        x: 12
                                        y: 12
                                        width: parent.width - 24
                                        spacing: 7
                                        RowLayout {
                                            width: parent.width
                                            height: implicitHeight
                                            spacing: 10
                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.title
                                                wrapMode: Text.Wrap
                                                color: modelData.complete ? "#a8d0b0" : win.textMain
                                                font.pixelSize: 13
                                                font.weight: Font.DemiBold
                                            }

                                        }
                                        Flow {
                                            width: parent.width; spacing: 8
                                            Rectangle {
                                                width: stateLabel.implicitWidth + 18; height: 28; radius: 4; color: "#222a32"
                                                Label { id: stateLabel; anchors.centerIn: parent; color: modelData.complete ? win.success : modelData.state === "available" ? "#8cd7bb" : modelData.state === "blocked" ? win.danger : win.muted
                                                    text: ({done:"已完成",available:"可进行",future:"未到达",blocked:"已阻断",missed:"分支未选",superseded:"已被替代",implied:"后续推定"})[modelData.state] || modelData.state }
                                            }
                                            Rectangle {
                                                width: typeLabel.implicitWidth + 18; height: 28; radius: 14; color: win.goldDim
                                                Label { id: typeLabel; anchors.centerIn: parent; color: win.goldHi; text: modelData.guideOnly ? "指引步骤" : "自动步骤" }
                                            }
                                            AppSwitch {
                                                objectName: "questStepSwitch_" + modelData.id
                                                visible: modelData.manualEligible
                                                enabled: backend.activeSlot >= 0 && (modelData.manual || (!modelData.complete && modelData.state !== "missed"))
                                                text: modelData.source === "inferred" ? "后续自动确认" : "手动完成"
                                                checked: modelData.complete
                                                onToggled: backend.setQuestStepChecked(modelData.questId, modelData.id, checked)
                                            }
                                        }
                                        Label {
                                            width: parent.width
                                            visible: text.length > 0
                                            text: modelData.action
                                            wrapMode: Text.Wrap
                                            lineHeight: 1.35
                                            color: win.muted
                                            font.pixelSize: 12
                                        }
                                        Label {
                                            visible: modelData.reward.length > 0
                                            width: parent.width
                                            text: "奖励：" + modelData.reward
                                            wrapMode: Text.Wrap
                                            color: "#d7bb84"
                                            font.pixelSize: 12
                                        }
                                        AppButton {
                                            visible: modelData.anchor.length > 0
                                            text: "在地图定位 →"
                                            flat: true
                                            contentAlignment: Text.AlignLeft
                                            width: implicitWidth
                                            onClicked: questRoot.locateRequested(modelData.anchor)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    component CatalogPage: Rectangle {
        id: catalogRoot
        objectName: "catalogRoot"
        signal locateRequested(string markerId)
        property var selectedItem: ({})
        color: win.bg2
        property var catalogModel: []
        ListModel { id: catalogRows; objectName: "catalogRows"; dynamicRoles: true }
        property string selectedCategory: "all"
        property string packFilter: "全部内容"
        property var categories: []
        property bool refreshPending: true
        property string appliedFilters: ""
        property string appliedRows: ""
        onVisibleChanged: if (visible && refreshPending) refresh()

        function refresh() {
            refreshPending = true
            if (visible) catalogRefresh.restart()
        }
        Timer { id: catalogRefresh; interval: 100; onTriggered: catalogRoot.applyRefresh() }
        function applyRefresh() {
            if (!visible) return
            // Replacing a GridView model interrupts its active scroll gesture.
            if (catalogScrollBar.pressed || catalogGrid.moving) return
            refreshPending = false
            var nextCategories = backend.catalogCategories()
            if (categories.some(function(c) { return c.id === selectedCategory }) &&
                !nextCategories.some(function(c) { return c.id === selectedCategory })) selectedCategory = "all"
            if ((packFilter === "黄金树幽影" && backend.contentPacks.dlc === "hide") ||
                (packFilter === "褪色者礼包" && backend.contentPacks.tarnished === "hide")) packFilter = "全部内容"
            if (JSON.stringify(categories) !== JSON.stringify(nextCategories)) categories = nextCategories
            var filters = JSON.stringify([selectedCategory, catalogSearch.text, missingOnly.checked, packFilter])
            var rows = backend.catalogItems(selectedCategory, catalogSearch.text, missingOnly.checked).filter(function(item) {
                return catalogRoot.packFilter === "全部内容" || (catalogRoot.packFilter === "本体" ? !item.pack : item.pack === catalogRoot.packFilter)
            })
            var signature = JSON.stringify(rows)
            var offset = catalogGrid.contentY - catalogGrid.originY
            if (signature !== appliedRows) {
                catalogModel = rows
                win.syncRows(catalogRows, rows, "key")
                catalogGrid.forceLayout()
                appliedRows = signature
            }
            if (filters !== appliedFilters) catalogGrid.positionViewAtBeginning()
            else catalogGrid.contentY = catalogGrid.originY + Math.max(0, Math.min(offset, catalogGrid.contentHeight - catalogGrid.height))
            appliedFilters = filters
            if (catalogDetail.opened) {
                var selected = rows.find(function(row) { return row.key === selectedItem.key })
                if (selected) selectedItem = selected
                else catalogDetail.close()
            }
        }
        function detailSections(details) {
            var d = details || {}
            var sections = []
            function values(title, labels, data, suffix) {
                if (!data || !data.length) return
                var rows = []
                for (var i = 0; i < Math.min(labels.length, data.length); ++i)
                    rows.push({ label: labels[i], value: data[i] + (suffix || "") })
                sections.push({ title: title, rows: rows })
            }
            values("攻击力", ["物理", "魔力", "火焰", "雷电", "神圣"], d.attack)
            values("能力要求", ["力量", "灵巧", "智力", "信仰", "感应"], d.requirements)
            values("能力加成系数", ["力量", "灵巧", "智力", "信仰", "感应"], d.scaling)
            values("防御时减伤率", ["物理", "魔力", "火焰", "雷电", "神圣"], d.guard, "%")
            values("伤害减伤率", ["物理", "魔力", "火焰", "雷电", "神圣"], d.negation, "%")
            values("异常状态抗性", ["毒", "猩红腐败", "出血", "冻伤", "睡眠", "发狂"], d.resistance || d.status_guard)
            if (d.poise !== undefined) sections.push({ title: "韧性系数", rows: [{label: "基础系数", value: d.poise}] })
            if (d.weight !== undefined) sections.push({ title: "基本信息", rows: [{label: "重量", value: d.weight}, {label: "售价", value: d.price !== undefined ? d.price : "-"}] })
            if (d.maxNum !== undefined || d.consumable !== undefined) sections.push({ title: "使用信息", rows: [
                {label: "可消耗", value: d.consumable ? "是" : "否"}, {label: "随身上限", value: d.maxNum !== undefined ? d.maxNum : "-"},
                {label: "仓库上限", value: d.maxRepositoryNum !== undefined ? d.maxRepositoryNum : "-"}, {label: "FP 消耗", value: d.consumeMP !== undefined ? d.consumeMP : "-"},
                {label: "HP 消耗", value: d.consumeHP !== undefined && d.consumeHP >= 0 ? d.consumeHP : "-"}
            ] })
            return sections
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Label { text: "收集品图鉴"; font.pixelSize: 23; font.weight: Font.DemiBold; color: win.textMain }
                Item { Layout.fillWidth: true }
                Label { text: backend.activeCharacter.name || "未选择角色"; color: win.goldHi; font.pixelSize: 12 }
            }
            Label { text: "背包与仓库合并 · 已拥有优先 · 点击卡片查看详情和获取来源"; color: win.muted; font.pixelSize: 11 }
            Flow {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                spacing: 6
                Repeater {
                    model: catalogRoot.categories
                    delegate: Button {
                        id: categoryTab
                        required property var modelData
                        text: modelData.name
                        checked: catalogRoot.selectedCategory === modelData.id
                        implicitWidth: tabLabel.implicitWidth + 24
                        implicitHeight: 30
                        padding: 0
                        onClicked: { catalogRoot.selectedCategory = modelData.id; catalogRoot.refresh() }
                        contentItem: Label {
                            id: tabLabel
                            text: categoryTab.text
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: categoryTab.checked ? win.goldHi : win.muted
                            font.pixelSize: 12
                        }
                        background: Rectangle {
                            radius: height / 2
                            color: categoryTab.checked ? "#332c20" : categoryTab.hovered ? win.panel2 : win.panel
                            border.width: 1
                            border.color: categoryTab.checked ? win.gold : win.border
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                AppField {
                    id: catalogSearch
                    Layout.fillWidth: true
                    placeholderText: "搜索名称、内容包或物品 ID…"
                    onTextChanged: catalogRoot.refresh()
                }
                AppComboBox {
                    Layout.preferredWidth: 150
                    model: ["全部内容", "本体"].concat(backend.contentPacks.dlc !== "hide" ? ["黄金树幽影"] : []).concat(backend.contentPacks.tarnished !== "hide" ? ["褪色者礼包"] : [])
                    currentIndex: model.indexOf(catalogRoot.packFilter)
                    onActivated: { catalogRoot.packFilter = currentText; catalogRoot.refresh() }
                }
                AppCheckBox {
                    id: missingOnly
                    text: "仅显示缺失"
                    checked: backend.displaySettings.catalogHideCompleted
                    enabled: backend.activeSlot >= 0
                    onToggled: backend.setDisplaySetting("catalogHideCompleted", checked)
                    onCheckedChanged: catalogRoot.refresh()
                }
                Label { text: catalogRoot.catalogModel.length + " 项"; color: win.subtle; font.pixelSize: 11 }
            }
            GridView {
                id: catalogGrid
                objectName: "catalogGrid"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                cellWidth: width / Math.max(1, Math.floor(width / 156))
                cellHeight: 178
                model: catalogRows
                onMovementEnded: if (catalogRoot.refreshPending) catalogRoot.refresh()
                ScrollBar.vertical: ScrollBar {
                    id: catalogScrollBar
                    objectName: "catalogScrollBar"
                    policy: ScrollBar.AsNeeded
                    onPressedChanged: if (!pressed && catalogRoot.refreshPending) catalogRoot.refresh()
                }
                delegate: Item {
                    required property var payload
                    property var modelData: payload
                    width: catalogGrid.cellWidth
                    height: catalogGrid.cellHeight
                    Rectangle {
                        anchors.fill: parent
                        anchors.rightMargin: 8
                        anchors.bottomMargin: 8
                        radius: 9
                        color: cardMouse.containsMouse ? win.panel2 : win.panel
                        border.width: 1
                        border.color: modelData.owned ? "#41664b" : win.border
                        MouseArea {
                            id: cardMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { catalogRoot.selectedItem = modelData; catalogDetail.open() }
                        }
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 3
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                Label { text: modelData.categoryName; color: win.subtle; font.pixelSize: 10; elide: Text.ElideRight; Layout.minimumWidth: 0 }
                                Rectangle {
                                    visible: !!modelData.pack
                                    Layout.preferredWidth: packLabel.implicitWidth + 8
                                    Layout.maximumWidth: 76
                                    Layout.preferredHeight: 17
                                    radius: 3
                                    color: modelData.pack === "褪色者礼包" ? "#254b61" : "#514021"
                                    Label {
                                        id: packLabel
                                        anchors.fill: parent; anchors.leftMargin: 4; anchors.rightMargin: 4
                                        text: modelData.pack; elide: Text.ElideRight
                                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                        color: modelData.pack === "褪色者礼包" ? "#bceaff" : "#ffe0a0"
                                        font.pixelSize: 10
                                    }
                                }
                                Item { Layout.fillWidth: true }
                                Label { visible: modelData.owned; text: "✓"; color: "#9dcca8"; font.pixelSize: 12 }
                            }
                            Image {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 54; Layout.preferredHeight: 54
                                source: backend.assetsRoot + "icons/" + modelData.icon
                                fillMode: Image.PreserveAspectFit; asynchronous: true
                            }
                            Label {
                                text: modelData.name
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                                color: win.textMain; font.pixelSize: 12
                            }
                            Label {
                                Layout.alignment: Qt.AlignHCenter
                                text: modelData.owned ? "已拥有" + (modelData.quantity > 1 ? " ×" + modelData.quantity : "") : "未收集"
                                color: modelData.owned ? "#9dcca8" : win.subtle
                                font.pixelSize: 10
                            }
                        }
                        ToolTip.visible: cardMouse.containsMouse
                        ToolTip.text: modelData.name
                        ToolTip.delay: 600
                    }
                }
                Label {
                    anchors.centerIn: parent
                    visible: catalogRoot.catalogModel.length === 0
                    text: "没有符合条件的收集品"
                    color: win.muted
                }
            }
        }

        Popup {
            id: catalogDetail
            objectName: "catalogDetail"
            onOpened: itemDetailScroll.contentItem.contentY = 0
            anchors.centerIn: parent; width: Math.min(720, catalogRoot.width - 32)
            height: Math.min(650, catalogRoot.height - 24); padding: 20; modal: true
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
            background: Rectangle { color: win.panel; radius: 14; border.color: win.borderStrong }
            contentItem: ScrollView {
                id: itemDetailScroll; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Column {
                    width: itemDetailScroll.availableWidth; spacing: 14
                    RowLayout {
                        width: parent.width; spacing: 16
                        Image { Layout.preferredWidth: 76; Layout.preferredHeight: 76; source: catalogRoot.selectedItem.icon ? backend.assetsRoot + "icons/" + catalogRoot.selectedItem.icon : ""; fillMode: Image.PreserveAspectFit }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 6
                            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: catalogRoot.selectedItem.name || ""; font.pixelSize: 22; font.bold: true; color: win.textMain }
                            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: (catalogRoot.selectedItem.categoryName || "") + " · " + (catalogRoot.selectedItem.pack || "本体"); color: catalogRoot.selectedItem.pack === "褪色者礼包" ? "#99d8f5" : win.goldHi }
                            Label { text: catalogRoot.selectedItem.owned ? "已拥有 × " + catalogRoot.selectedItem.quantity : "未收集"; color: catalogRoot.selectedItem.owned ? win.success : win.muted }
                        }
                        AppButton { text: "×"; implicitWidth: 32; onClicked: catalogDetail.close(); Accessible.name: "关闭详情" }
                    }
                    Repeater {
                        model: catalogRoot.detailSections(catalogRoot.selectedItem.details)
                        delegate: Column {
                            required property var modelData
                            width: parent.width; spacing: 8
                            Rectangle { width: parent.width; height: 1; color: win.border }
                            Label { text: modelData.title; font.pixelSize: 13; font.bold: true; color: win.goldHi }
                            Grid {
                                width: parent.width; columns: width >= 480 ? 3 : 2; columnSpacing: 12; rowSpacing: 4
                                Repeater {
                                    model: modelData.rows
                                    delegate: RowLayout {
                                        required property var modelData
                                        width: (parent.width - parent.columnSpacing * (parent.columns - 1)) / parent.columns
                                        height: 32; spacing: 8
                                        Label { Layout.fillWidth: true; text: modelData.label; color: win.muted; font.pixelSize: 12; elide: Text.ElideRight }
                                        Label { text: modelData.value; color: Number(modelData.value) === 0 || modelData.value === "-" ? win.subtle : win.textMain; font.pixelSize: 16; font.weight: Font.DemiBold }
                                    }
                                }
                            }
                        }
                    }
                    Rectangle { width: parent.width; height: 1; color: win.border }
                    Label { text: "物品说明"; font.pixelSize: 13; font.bold: true; color: win.goldHi }
                    Label { width: parent.width; wrapMode: Text.Wrap; text: catalogRoot.selectedItem.description || "当前游戏文本未提供物品描述。"; color: win.muted; lineHeight: 1.4; font.pixelSize: 13 }
                    Label { text: "获取方式"; font.bold: true }
                    Label { visible: !(catalogRoot.selectedItem.sources || []).length; text: "当前解析数据未提供可靠的获取来源。"; color: win.subtle }
                    Repeater {
                        model: catalogRoot.selectedItem.sources || []
                        delegate: Column {
                            required property var modelData
                            width: parent.width; spacing: 4
                            Label { width: parent.width; wrapMode: Text.Wrap; text: modelData.text; color: win.muted }
                            AppButton { visible: !!modelData.marker; text: "在地图定位"; onClicked: { catalogDetail.close(); catalogRoot.locateRequested(modelData.marker) } }
                        }
                    }
                    Label { visible: !!catalogRoot.selectedItem.iconFallback; text: "此项使用类别图标（尚未提取物品原图）"; color: win.subtle; font.pixelSize: 11 }
                }
            }
        }
    }

    component SettingsPage: Rectangle {
        id: settingsRoot
        color: win.bg2

        ScrollView {
            id: settingsScroll
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.topMargin: 18
            anchors.bottomMargin: 18
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: Math.min(900, settingsScroll.availableWidth)
                x: Math.max(0, (settingsScroll.availableWidth - width) / 2)
                spacing: 12

                ColumnLayout {
                    spacing: 2
                    Label { text: "设置"; font.pixelSize: 23; font.weight: Font.DemiBold; color: win.textMain }
                    Label { text: "管理游戏资源缓存、存档来源和角色手动状态。"; color: win.muted; font.pixelSize: 11 }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: resourceSettings.implicitHeight + 36
                    radius: 12
                    color: win.panel
                    border.width: 1
                    border.color: win.border
                    ColumnLayout {
                        id: resourceSettings
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 18
                        spacing: 9
                        Label { text: "游戏资源"; font.pixelSize: 16; font.weight: Font.DemiBold; color: win.textMain }
                        Label {
                            text: "当前资源路径。重新解析适用于游戏更新、模组切换或资源异常。"
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: win.muted
                            font.pixelSize: 11
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            radius: 7
                            color: "#0e1217"
                            border.width: 1
                            border.color: win.border
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 11
                                anchors.rightMargin: 11
                                text: backend.gameDir || "未选择游戏目录"
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideMiddle
                                color: win.muted
                                font.family: "Consolas"
                                font.pixelSize: 10
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 9
                            AppButton { text: "重新解析游戏资源"; tone: "primary"; onClicked: backend.reparse() }
                            AppButton { text: "清理解析缓存"; tone: "danger"; onClicked: backend.clearScanCache() }
                            Item { Layout.fillWidth: true }
                        }
                        Label {
                            text: "清理解析缓存不会删除角色手动收集记录、任务确认或任务定义。"
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: win.subtle
                            font.pixelSize: 10
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: saveSettings.implicitHeight + 36
                    radius: 12
                    color: win.panel
                    border.width: 1
                    border.color: win.border
                    ColumnLayout {
                        id: saveSettings
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 18
                        spacing: 9
                        Label { text: "存档与角色状态"; font.pixelSize: 16; font.weight: Font.DemiBold; color: win.textMain }
                        Label { text: "手动路径优先；留空使用自动查找。支持 .sl2、.co2、.err。"; color: win.muted; font.pixelSize: 11 }
                        RowLayout {
                            Layout.fillWidth: true
                            AppField {
                                id: savePathInput
                                objectName: "savePathInput"
                                Layout.fillWidth: true
                                text: backend.configuredSavePath
                                placeholderText: "输入存档文件的完整路径"
                                selectByMouse: true
                                onAccepted: backend.setSavePath(text)
                            }
                            AppButton { text: "应用路径"; onClicked: backend.setSavePath(savePathInput.text) }
                            AppButton { text: "恢复自动查找"; onClicked: { backend.setSavePath(""); savePathInput.text = Qt.binding(function() { return backend.configuredSavePath }) } }
                        }
                        Label {
                            Layout.fillWidth: true; wrapMode: Text.WrapAnywhere
                            text: "当前已读取：" + (backend.currentSavePath || "尚未读取存档")
                            color: win.subtle; font.pixelSize: 11
                        }
                        Connections {
                            target: backend
                            function onSavePathChanged() { savePathInput.text = Qt.binding(function() { return backend.configuredSavePath }) }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Label { text: "存档变化轮询间隔（秒）"; color: win.muted }
                            AppField {
                                objectName: "savePollIntervalInput"
                                Layout.preferredWidth: 100
                                text: backend.savePollInterval.toFixed(1)
                                inputMethodHints: Qt.ImhFormattedNumbersOnly
                                validator: DoubleValidator { bottom: 0.2; top: 60; decimals: 1; notation: DoubleValidator.StandardNotation; locale: "C" }
                                onEditingFinished: {
                                    if (acceptableInput) backend.setSavePollInterval(Number(text))
                                    text = Qt.binding(function() { return backend.savePollInterval.toFixed(1) })
                                }
                            }
                            Label { text: "0.2–60 秒"; color: win.subtle; font.pixelSize: 11 }
                            Item { Layout.fillWidth: true }
                        }
                        Label {
                            text: "存档只读；地图手动勾选按 Steam/存档账号目录 + 角色槽位 + 角色名隔离。"
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: win.muted
                            font.pixelSize: 11
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 9
                            AppButton { text: "手动选择存档文件"; onClicked: saveDialog.open() }
                            AppButton { text: "立即刷新存档"; onClicked: backend.refresh_save(true) }
                            AppButton {
                                objectName: "journeyResetButton"
                                text: "周目重置"
                                enabled: backend.activeSlot >= 0 && !!backend.currentSavePath
                                onClicked: {
                                    journeyResetDialog.resetTarget = backend.manualResetTarget()
                                    if (journeyResetDialog.resetTarget.scope) journeyResetDialog.open()
                                }
                            }
                            AppButton {
                                text: "导入旧版共享地图勾选"
                                enabled: backend.activeSlot >= 0 && backend.legacyMarkerCount() > 0
                                onClicked: backend.importLegacyMarkerChecks()
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Label {
                            visible: backend.legacyMarkerCount() > 0
                            text: "检测到旧版共享地图勾选 " + backend.legacyMarkerCount() + " 项。它们不会自动应用到任何角色；请切换到目标角色后手动导入。"
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            color: "#d7bb84"
                            font.pixelSize: 10
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: contentSettings.implicitHeight + 36
                    radius: 12; color: win.panel; border.color: win.border
                    ColumnLayout {
                        id: contentSettings
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 18
                        spacing: 9
                        Label { text: "DLC 内容显示"; font.pixelSize: 16; color: win.textMain }
                        Label {
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                            text: "购买状态无法从本地资源可靠确认。读取存档后，请按使用的内容分别设置；隐藏会同时影响图鉴、任务和已知关联地图标记。设置随当前存档保存，未确认时保留显示。"
                            color: win.muted; font.pixelSize: 11
                        }
                        Repeater {
                            model: [{key: "dlc", name: "黄金树幽影"}, {key: "tarnished", name: "褪色者礼包"}]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Label { text: modelData.name; color: win.textMain; Layout.fillWidth: true }
                                AppComboBox {
                                    Layout.preferredWidth: 210
                                    model: ["未确认 · 保留显示", "拥有 / 启用 · 显示", "未购买 / 不使用 · 隐藏"]
                                    enabled: !!backend.currentSavePath
                                    currentIndex: ["unknown", "show", "hide"].indexOf(backend.contentPacks[modelData.key])
                                    onActivated: backend.setContentPack(modelData.key, ["unknown", "show", "hide"][currentIndex])
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: safetySettings.implicitHeight + 36
                    radius: 12
                    color: win.panel
                    border.width: 1
                    border.color: win.border
                    ColumnLayout {
                        id: safetySettings
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 18
                        spacing: 9
                        Label { text: "安全说明"; font.pixelSize: 16; font.weight: Font.DemiBold; color: win.textMain }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: safeText.implicitHeight + 24
                            radius: 9
                            color: "#142019"
                            border.width: 1
                            border.color: "#284534"
                            Label {
                                id: safeText
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                text: "EldenRingTool 只读 Elden Ring 游戏资源和 ER0000.sl2。手动收集状态与 guide-only 任务确认只写入 data/user-state.json。存档轮询在后台线程执行，游戏自动保存时界面不会等待完整的 MD5/AES 校验。"
                                wrapMode: Text.Wrap
                                lineHeight: 1.35
                                color: "#a9c8af"
                                font.pixelSize: 11
                            }
                        }
                    }
                }

                Label {
                    text: "EldenRingTool 0.1.0 · Python 3.13+ · PySide6 + QML"
                    color: win.subtle
                    font.pixelSize: 10
                    Layout.alignment: Qt.AlignHCenter
                    Layout.bottomMargin: 18
                }
            }
        }
    }

}
