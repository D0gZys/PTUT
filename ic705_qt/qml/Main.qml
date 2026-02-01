import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
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
    property int wfDepth: 200
    property int wfBottomIndex: Math.max(0, csvReplay.currentIndex - wfDepth + 1)
    property string csvWfTopTime: csvReplay.loaded ? csvReplay.currentTimestamp : "--"
    property string csvWfBottomTime: csvReplay.loaded ? csvReplay.timestampAt(wfBottomIndex) : "--"
    property string defaultRadioIp: "192.168.59.1"
    property string defaultRadioUser: "IC-705-7"
    property string defaultRadioPass: "bouter20xx"
    property string defaultRadioName: "IC-705-7"
    property string defaultRadioMac: "00:90:C7:13:CA:75"
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

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label { text: "Min (dBm):" }
            Slider {
                id: minSlider
                from: -160
                to: -60
                stepSize: 1
                value: liveSpectrumModel.dbmMin
                onMoved: {
                    var minVal = value
                    var maxVal = maxSlider.value
                    if (minVal >= maxVal) {
                        minVal = maxVal - 1
                        value = minVal
                    }
                    liveSpectrumModel.setDbmRange(minVal, maxVal)
                    liveWaterfallModel.setDbmRange(minVal, maxVal)
                    replaySpectrumModel.setDbmRange(minVal, maxVal)
                    replayWaterfallModel.setDbmRange(minVal, maxVal)
                }
            }
            Label { text: minSlider.value.toFixed(0) }

            Label { text: "Max (dBm):" }
            Slider {
                id: maxSlider
                from: -160
                to: -60
                stepSize: 1
                value: liveSpectrumModel.dbmMax
                onMoved: {
                    var minVal = minSlider.value
                    var maxVal = value
                    if (maxVal <= minVal) {
                        maxVal = minVal + 1
                        value = maxVal
                    }
                    liveSpectrumModel.setDbmRange(minVal, maxVal)
                    liveWaterfallModel.setDbmRange(minVal, maxVal)
                    replaySpectrumModel.setDbmRange(minVal, maxVal)
                    replayWaterfallModel.setDbmRange(minVal, maxVal)
                }
            }
            Label { text: maxSlider.value.toFixed(0) }
            Button {
                text: "Reset"
                onClicked: {
                    minSlider.value = -160
                    maxSlider.value = -80
                    liveSpectrumModel.setDbmRange(minSlider.value, maxSlider.value)
                    liveWaterfallModel.setDbmRange(minSlider.value, maxSlider.value)
                    replaySpectrumModel.setDbmRange(minSlider.value, maxSlider.value)
                    replayWaterfallModel.setDbmRange(minSlider.value, maxSlider.value)
                }
            }
        }

        StackLayout {
            id: modeStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: modeTabs.currentIndex

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
                    Label {
                        text: csvRecorder.statusText
                        Layout.fillWidth: true
                    }
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
                                Label {
                                    text: dbmMax.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: dbmMid.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: dbmMin.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    font.pixelSize: 10
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: "transparent"

                                SpectrumItem {
                                    anchors.fill: parent
                                    model: liveSpectrumModel
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

                                Label {
                                    text: liveFreqMin.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignLeft
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: liveCenterFreq.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: liveFreqMax.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    font.pixelSize: 10
                                }
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
                                Label {
                                    text: "--"
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: "--"
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    font.pixelSize: 10
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: "transparent"

                                WaterfallItem {
                                    anchors.fill: parent
                                    model: liveWaterfallModel
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

                                Label {
                                    text: liveFreqMin.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignLeft
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: liveCenterFreq.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: liveFreqMax.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label { text: "CSV:" }
                    TextField {
                        id: csvPath
                        Layout.fillWidth: true
                        placeholderText: "C:\\...\\file.csv"
                    }
                    Button {
                        text: "Parcourir"
                        onClicked: fileDialog.open()
                    }
                    Button { text: "Charger"; onClicked: csvReplay.loadFile(csvPath.text) }
                    Button { text: "<"; enabled: csvReplay.loaded && csvReplay.currentIndex > 0; onClicked: csvReplay.prev() }
                    Button { text: ">"; enabled: csvReplay.loaded && csvReplay.currentIndex + 1 < csvReplay.lineCount; onClicked: csvReplay.next() }
                    Label {
                        text: csvReplay.loaded ? ("CSV " + (csvReplay.currentIndex + 1) + "/" + csvReplay.lineCount + " " + csvReplay.currentTimestamp) : "CSV: aucun"
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        text: csvReplay.playing ? "Pause" : "Play"
                        enabled: csvReplay.loaded
                        onClicked: csvReplay.togglePlay()
                    }
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

                Label {
                    text: csvReplay.lastError
                    visible: csvReplay.lastError.length > 0
                    color: "#ff6666"
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
                                Label {
                                    text: dbmMax.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: dbmMid.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: dbmMin.toFixed(0)
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    font.pixelSize: 10
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: "transparent"

                                SpectrumItem {
                                    anchors.fill: parent
                                    model: replaySpectrumModel
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

                                Label {
                                    text: csvFreqMin.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignLeft
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: csvCenterFreq.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: csvFreqMax.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    font.pixelSize: 10
                                }
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
                                Label {
                                    text: csvWfTopTime
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: csvWfBottomTime
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    font.pixelSize: 10
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: "transparent"

                                WaterfallItem {
                                    anchors.fill: parent
                                    model: replayWaterfallModel
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

                                Label {
                                    text: csvFreqMin.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignLeft
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: csvCenterFreq.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: csvFreqMax.toFixed(6)
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignRight
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: fileDialog
        title: "Ouvrir CSV"
        nameFilters: ["CSV files (*.csv)", "All files (*)"]
        onAccepted: {
            csvPath.text = fileDialog.selectedFile
            csvReplay.loadFile(csvPath.text)
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
}
