import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQml
import IC705

Window {
    width: 1000
    height: 600
    visible: true
    title: "IC705 Qt - Step 1"

    property real defaultFreq: 7.1
    property real defaultSpanKhz: 5.0

    property real liveCenterFreq: civClient.freqMHz > 0 ? civClient.freqMHz : defaultFreq
    property real liveSpanKhz: defaultSpanKhz
    property real liveFreqMin: liveCenterFreq - liveSpanKhz / 2000.0
    property real liveFreqMax: liveCenterFreq + liveSpanKhz / 2000.0

    property real csvCenterFreq: csvReplay.loaded && csvReplay.currentFreqMHz > 0 ? csvReplay.currentFreqMHz : defaultFreq
    property real csvSpanKhz: csvReplay.loaded && csvReplay.currentSpanKHz > 0 ? csvReplay.currentSpanKHz : defaultSpanKhz
    property real csvFreqMin: csvCenterFreq - csvSpanKhz / 2000.0
    property real csvFreqMax: csvCenterFreq + csvSpanKhz / 2000.0

    property real dbmMin: liveSpectrumModel.dbmMin
    property real dbmMax: liveSpectrumModel.dbmMax
    property real dbmMid: (dbmMin + dbmMax) / 2.0

    property real csvDbmMin: replaySpectrumModel.dbmMin
    property real csvDbmMax: replaySpectrumModel.dbmMax
    property real csvDbmMid: (csvDbmMin + csvDbmMax) / 2.0

    property int wfDepth: 200
    property int wfBottomIndex: Math.max(0, csvReplay.currentIndex - wfDepth + 1)
    property string csvWfTopTime: csvReplay.loaded ? csvReplay.currentTimestamp : "--"
    property string csvWfBottomTime: csvReplay.loaded ? csvReplay.timestampAt(wfBottomIndex) : "--"
    property bool csvMarkersEnabled: true

    property string defaultRadioIp: "192.168.59.1"
    property string defaultRadioUser: "IC-705-7"
    property string defaultRadioPass: "bouter20xx"
    property string defaultRadioName: "IC-705-7"
    property string defaultRadioMac: "00:90:C7:13:CA:75"

    property string csvPath: ""

    ListModel { id: csvMarkersModel }
    Connections {
        target: csvReplay
        function onLoadedChanged() {
            if (csvReplay.loaded) {
                csvMarkersModel.clear()
            }
        }
    }

    onLiveSpanKhzChanged: csvRecorder.setCurrentSpanKHz(liveSpanKhz)
    Component.onCompleted: csvRecorder.setCurrentSpanKHz(liveSpanKhz)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        TabBar {
            id: modeTabs
            Layout.fillWidth: true
            TabButton { text: "Live" }
            TabButton { text: "CSV" }
        }

        StackLayout {
            id: modeStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: modeTabs.currentIndex

            // ===== LIVE TAB =====
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Button {
                        text: civClient.connected ? "Deconnecter" : "Connecter"
                        onClicked: civClient.connected ? civClient.disconnectFromHost() : connectDialog.open()
                    }
                    Button { text: "Start"; enabled: false }
                    Label {
                        text: "Status: " + civClient.statusText + "  Freq: " + civClient.freqMHz.toFixed(3) + " MHz  Ref: " + civClient.refLevel + " dBm"
                        Layout.fillWidth: true
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Button {
                        text: csvRecorder.recording ? "STOP" : "REC"
                        enabled: civClient.connected
                        onClicked: csvRecorder.toggle()
                    }
                    CheckBox {
                        id: triggerCheck
                        text: "Trigger >"
                        checked: csvRecorder.triggerEnabled
                        enabled: !csvRecorder.recording
                        onToggled: csvRecorder.setTriggerEnabled(checked)
                    }
                    TextField {
                        id: triggerField
                        text: ""
                        Layout.preferredWidth: 80
                        enabled: !csvRecorder.recording
                        inputMethodHints: Qt.ImhFormattedNumbersOnly
                        Component.onCompleted: text = csvRecorder.triggerThreshold.toFixed(0)
                        onEditingFinished: {
                            var v = parseFloat(text)
                            if (isNaN(v)) {
                                text = csvRecorder.triggerThreshold.toFixed(0)
                                return
                            }
                            csvRecorder.setTriggerThreshold(v)
                            text = v.toFixed(0)
                        }
                    }
                    Label { text: "dBm" }
                    Label { text: csvRecorder.statusText; Layout.fillWidth: true }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 240
                    color: "#101820"
                    border.color: "#2a2a2a"
                    radius: 4

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 6

                            Item {
                                Layout.preferredWidth: 70
                                Layout.fillHeight: true
                                Label { text: "dBm"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10 }
                                Label { text: dbmMax.toFixed(0); anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10 }
                                Label { text: dbmMid.toFixed(0); anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10 }
                                Label { text: dbmMin.toFixed(0); anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10 }
                            }

                            SpectrumItem {
                                id: liveSpectrumDisplay
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                model: liveSpectrumModel
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 18
                            spacing: 6
                            Item { Layout.preferredWidth: 70 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label { text: liveFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10 }
                                Label { text: liveCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10 }
                                Label { text: liveFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10 }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "#0b0f12"
                    border.color: "#2a2a2a"
                    radius: 4

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 6

                            Item {
                                Layout.preferredWidth: 70
                                Layout.fillHeight: true
                                Label { text: "Temps"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10 }
                                Label { text: "--"; anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10 }
                                Label { text: "--"; anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10 }
                            }

                            WaterfallItem {
                                id: liveWaterfallDisplay
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                model: liveWaterfallModel
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 18
                            spacing: 6
                            Item { Layout.preferredWidth: 70 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label { text: liveFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10 }
                                Label { text: liveCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10 }
                                Label { text: liveFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10 }
                            }
                        }
                    }
                }
            }

            // ===== CSV TAB =====
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Button { text: "Selectionner CSV"; onClicked: csvFileDialog.open() }
                    Label { text: csvReplay.loaded ? (csvPath.split('/').pop().split('\\').pop()) : "Aucun fichier"; elide: Text.ElideMiddle; Layout.fillWidth: true }
                    Button { text: "<<"; enabled: csvReplay.loaded && csvReplay.currentIndex > 0; onClicked: csvReplay.setIndex(0); ToolTip.text: "Debut" }
                    Button { text: "<"; enabled: csvReplay.loaded && csvReplay.currentIndex > 0; onClicked: csvReplay.prev() }
                    Button { text: ">"; enabled: csvReplay.loaded && csvReplay.currentIndex + 1 < csvReplay.lineCount; onClicked: csvReplay.next() }
                    Button { text: ">>"; enabled: csvReplay.loaded && csvReplay.currentIndex + 1 < csvReplay.lineCount; onClicked: csvReplay.setIndex(csvReplay.lineCount - 1); ToolTip.text: "Fin" }
                    Label { text: csvReplay.loaded ? ((csvReplay.currentIndex + 1) + "/" + csvReplay.lineCount + " | " + csvReplay.currentTimestamp) : "" }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Button { text: csvReplay.playing ? "Pause" : "Play"; enabled: csvReplay.loaded; onClicked: csvReplay.togglePlay() }
                    Button { text: "Jump to Max"; enabled: csvReplay.loaded; onClicked: jumpToMaxSignal() }
                    Label { text: "Position:" }
                    Slider {
                        id: positionSlider
                        Layout.fillWidth: true
                        from: 0
                        to: csvReplay.lineCount > 0 ? csvReplay.lineCount - 1 : 0
                        stepSize: 1
                        enabled: csvReplay.loaded
                        value: csvReplay.currentIndex
                        onMoved: csvReplay.setIndex(Math.round(value))
                    }
                    Label { text: "Vitesse:" }
                    ComboBox {
                        id: speedCombo
                        model: ["0.25x", "0.5x", "1x", "2x", "4x", "10x"]
                        currentIndex: 2
                        enabled: csvReplay.loaded
                        onActivated: {
                            var value = parseFloat(currentText)
                            if (!isNaN(value)) {
                                csvReplay.setSpeed(value)
                            }
                        }
                    }
                    Label { text: csvReplay.loaded ? ("x" + csvReplay.speed.toFixed(2)) : "" }
                }

                Label { text: csvReplay.lastError; visible: csvReplay.lastError.length > 0; color: "#ff6666" }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 8

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 240
                            color: "#101820"
                            border.color: "#2a2a2a"
                            radius: 4

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 4

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    spacing: 6
                                    Item {
                                        Layout.preferredWidth: 70
                                        Layout.fillHeight: true
                                        Label { text: "dBm"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10 }
                                        Label { text: csvDbmMax.toFixed(0); anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10 }
                                        Label { text: csvDbmMid.toFixed(0); anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10 }
                                        Label { text: csvDbmMin.toFixed(0); anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10 }
                                    }
                                    SpectrumItem { id: csvSpectrumDisplay; Layout.fillWidth: true; Layout.fillHeight: true; model: replaySpectrumModel }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 18
                                    spacing: 6
                                    Item { Layout.preferredWidth: 70 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 0
                                        Label { text: csvFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10 }
                                        Label { text: csvCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10 }
                                        Label { text: csvFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10 }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            color: "#0b0f12"
                            border.color: "#2a2a2a"
                            radius: 4

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 4

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    spacing: 6
                                    Item {
                                        Layout.preferredWidth: 70
                                        Layout.fillHeight: true
                                        Label { text: "Temps"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10 }
                                        Label { text: csvWfTopTime; anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10 }
                                        Label { text: csvWfBottomTime; anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10 }
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        WaterfallItem { id: csvWaterfallDisplay; anchors.fill: parent; model: replayWaterfallModel }

                                        WheelHandler {
                                            onWheel: function (wheel) {
                                                if (!csvReplay.loaded) return
                                                var delta = wheel.angleDelta.y
                                                if (delta === 0) return
                                                var step = (wheel.modifiers & Qt.ShiftModifier) ? 10 : 1
                                                var dir = delta > 0 ? -1 : 1
                                                csvReplay.setIndex(csvReplay.currentIndex + dir * step)
                                            }
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            onClicked: {
                                                if (!csvMarkersEnabled) return
                                                var xr = mouse.x / width
                                                var yr = mouse.y / height
                                                var xIdx = Math.round(xr * (replayWaterfallModel.width - 1))
                                                var yIdx = Math.round(yr * (replayWaterfallModel.height - 1))
                                                var freq = csvFreqMin + (xIdx / (replayWaterfallModel.width - 1)) * (csvFreqMax - csvFreqMin)
                                                var dbm = replayWaterfallModel.valueAt(xIdx, yIdx)
                                                var timeText = csvReplay.loaded ? csvReplay.timestampAt(csvReplay.currentIndex - yIdx) : "CSV"
                                                csvMarkersModel.append({ xr: xr, yr: yr, freq: freq, dbm: dbm, time: timeText })
                                            }
                                        }

                                        Repeater {
                                            model: csvMarkersModel
                                            delegate: Item {
                                                anchors.fill: parent
                                                property real px: model.xr * width
                                                property real py: model.yr * height
                                                Rectangle { x: px - 3; y: py - 3; width: 6; height: 6; radius: 3; color: "#ffff00" }
                                                Rectangle {
                                                    id: markerLabelBg
                                                    width: markerLabel.implicitWidth + 8
                                                    height: markerLabel.implicitHeight + 4
                                                    x: px + (px > parent.width * 0.6 ? -width - 6 : 6)
                                                    y: py + (py > parent.height * 0.6 ? -height - 6 : 6)
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: "#ffff00"
                                                    radius: 3
                                                    Text { id: markerLabel; anchors.centerIn: parent; text: model.freq.toFixed(6) + " MHz  " + model.dbm.toFixed(1) + " dBm  " + model.time; color: "white"; font.pixelSize: 9 }
                                                }
                                            }
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 18
                                    spacing: 6
                                    Item { Layout.preferredWidth: 70 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 0
                                        Label { text: csvFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10 }
                                        Label { text: csvCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10 }
                                        Label { text: csvFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10 }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 240
                        Layout.fillHeight: true
                        color: "#151b22"
                        border.color: "#2a2a2a"
                        radius: 4

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 10

                            GroupBox {
                                title: "Gain (dBm)"
                                Layout.fillWidth: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 6
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Label { text: "Max"; Layout.preferredWidth: 40 }
                                        Slider {
                                            id: csvDbmMaxSlider
                                            Layout.fillWidth: true
                                            from: -160
                                            to: -20
                                            stepSize: 1
                                            onMoved: {
                                                var v = Math.max(value, replaySpectrumModel.dbmMin + 1)
                                                replaySpectrumModel.dbmMax = v
                                                replayWaterfallModel.dbmMax = v
                                            }
                                        }
                                        Binding { target: csvDbmMaxSlider; property: "value"; value: replaySpectrumModel.dbmMax; when: !csvDbmMaxSlider.pressed }
                                        Label { text: replaySpectrumModel.dbmMax.toFixed(0); Layout.preferredWidth: 36 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Label { text: "Min"; Layout.preferredWidth: 40 }
                                        Slider {
                                            id: csvDbmMinSlider
                                            Layout.fillWidth: true
                                            from: -160
                                            to: -20
                                            stepSize: 1
                                            onMoved: {
                                                var v = Math.min(value, replaySpectrumModel.dbmMax - 1)
                                                replaySpectrumModel.dbmMin = v
                                                replayWaterfallModel.dbmMin = v
                                            }
                                        }
                                        Binding { target: csvDbmMinSlider; property: "value"; value: replaySpectrumModel.dbmMin; when: !csvDbmMinSlider.pressed }
                                        Label { text: replaySpectrumModel.dbmMin.toFixed(0); Layout.preferredWidth: 36 }
                                    }
                                    Button {
                                        text: "Reset"
                                        onClicked: {
                                            replaySpectrumModel.dbmMin = -160
                                            replaySpectrumModel.dbmMax = -80
                                            replayWaterfallModel.dbmMin = -160
                                            replayWaterfallModel.dbmMax = -80
                                        }
                                    }
                                }
                            }

                            GroupBox {
                                title: "Markers"
                                Layout.fillWidth: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 6
                                    CheckBox { text: csvMarkersEnabled ? "Markers ON" : "Markers OFF"; checked: csvMarkersEnabled; onToggled: csvMarkersEnabled = checked }
                                    Button { text: "Clear markers"; onClicked: csvMarkersModel.clear() }
                                }
                            }

                            GroupBox {
                                title: "Export"
                                Layout.fillWidth: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 6
                                    Button { text: "Export (TODO)"; enabled: false; ToolTip.visible: hovered; ToolTip.text: "Fonctionnalite en cours d'implementation" }
                                }
                            }

                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: csvFileDialog
        title: "Ouvrir CSV"
        nameFilters: ["CSV files (*.csv)", "All files (*)"]
        onAccepted: {
            csvPath = csvFileDialog.selectedFile
            csvReplay.loadFile(csvPath)
        }
    }

    Dialog {
        id: connectDialog
        title: "Connexion IC-705"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            civClient.connectWithParams(
                ipField.text,
                userField.text,
                passField.text,
                nameField.text,
                macField.text
            )
        }

        contentItem: ColumnLayout {
            spacing: 8
            RowLayout {
                spacing: 8
                Label { text: "IP:" }
                TextField { id: ipField; text: defaultRadioIp; Layout.preferredWidth: 200 }
            }
            RowLayout {
                spacing: 8
                Label { text: "User:" }
                TextField { id: userField; text: defaultRadioUser; Layout.preferredWidth: 200 }
            }
            RowLayout {
                spacing: 8
                Label { text: "Pass:" }
                TextField { id: passField; text: defaultRadioPass; echoMode: TextInput.Password; Layout.preferredWidth: 200 }
            }
            RowLayout {
                spacing: 8
                Label { text: "Name:" }
                TextField { id: nameField; text: defaultRadioName; Layout.preferredWidth: 200 }
            }
            RowLayout {
                spacing: 8
                Label { text: "MAC:" }
                TextField { id: macField; text: defaultRadioMac; Layout.preferredWidth: 200 }
            }
        }
    }

    function jumpToMaxSignal() {
        if (!csvReplay.loaded) return
        var maxIndex = csvReplay.findMaxSignalIndex()
        if (maxIndex >= 0) {
            csvReplay.setIndex(maxIndex)
        }
    }
}
