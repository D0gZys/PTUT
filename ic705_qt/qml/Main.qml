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
    property real centerFreq: csvReplay.loaded && csvReplay.currentFreqMHz > 0 ? csvReplay.currentFreqMHz
                               : (civClient.freqMHz > 0 ? civClient.freqMHz : defaultFreq)
    property real spanKhz: csvReplay.loaded && csvReplay.currentSpanKHz > 0 ? csvReplay.currentSpanKHz : defaultSpanKhz
    property real freqMin: centerFreq - spanKhz / 2000.0
    property real freqMax: centerFreq + spanKhz / 2000.0
    property real dbmMin: spectrumModel.dbmMin
    property real dbmMax: spectrumModel.dbmMax
    property real dbmMid: (dbmMin + dbmMax) / 2.0
    property int wfDepth: 200
    property int wfBottomIndex: Math.max(0, csvReplay.currentIndex - wfDepth + 1)
    property string wfTopTime: csvReplay.loaded ? csvReplay.currentTimestamp : "--"
    property string wfBottomTime: csvReplay.loaded ? csvReplay.timestampAt(wfBottomIndex) : "--"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                text: civClient.connected ? "Deconnecter" : "Connecter"
                onClicked: civClient.connected ? civClient.disconnectFromHost() : civClient.connectToDefault()
            }
            Button { text: "Start"; enabled: false }
            Button { text: "REC"; enabled: false }
            Label {
                text: "Status: " + civClient.statusText + "  Freq: " + civClient.freqMHz.toFixed(3) + " MHz  Ref: " + civClient.refLevel + " dBm"
                Layout.fillWidth: true
            }
        }

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

        FileDialog {
            id: fileDialog
            title: "Ouvrir CSV"
            nameFilters: ["CSV files (*.csv)", "All files (*)"]
            onAccepted: {
                csvPath.text = fileDialog.selectedFile
                csvReplay.loadFile(csvPath.text)
            }
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
                            model: spectrumModel
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
                            text: freqMin.toFixed(6)
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignLeft
                            font.pixelSize: 10
                        }
                        Label {
                            text: centerFreq.toFixed(6)
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: 10
                        }
                        Label {
                            text: freqMax.toFixed(6)
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
                            text: wfTopTime
                            anchors.right: parent.right
                            anchors.top: parent.top
                            font.pixelSize: 10
                        }
                        Label {
                            text: wfBottomTime
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
                            model: waterfallModel
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
                            text: freqMin.toFixed(6)
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignLeft
                            font.pixelSize: 10
                        }
                        Label {
                            text: centerFreq.toFixed(6)
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            font.pixelSize: 10
                        }
                        Label {
                            text: freqMax.toFixed(6)
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
