import QtQuick
import QtQuick.Window
import QtQuick.Shapes
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

    Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.onPressed: {
            if (event.key === Qt.Key_Escape && csvZoomMode) {
                csvZoomMode = false
                event.accepted = true
            }
        }
    }

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
    property real csvZoomX: 1.0
    property real csvZoomY: 1.0
    property real csvZoomMin: 1.0
    property real csvZoomMax: 8.0
    property real csvZoomCx: 0.5
    property real csvZoomCy: 0.5
    property bool csvZoomMode: false

    property int wfDepth: 200
    property int wfBottomIndex: Math.max(0, csvReplay.currentIndex - wfDepth + 1)
    property string csvWfTopTime: csvReplay.loaded ? csvReplay.currentTimestamp : "--"
    property string csvWfBottomTime: csvReplay.loaded ? csvReplay.timestampAt(wfBottomIndex) : "--"
    property bool csvMarkersEnabled: true
    property string csvNextMarkerColor: "#00ff66"
    property var csvMarkerColors: ["#00ff66", "#ff9900", "#00aaff", "#ff3366", "#ffffff"]
    property int maxSpectrumCursors: 2

    property string defaultRadioIp: "192.168.59.1"
    property string defaultRadioUser: "IC-705-7"
    property string defaultRadioPass: "bouter20xx"
    property string defaultRadioName: "IC-705-7"
    property string defaultRadioMac: "00:90:C7:13:CA:75"

    property string csvPath: ""
    property bool csvExportUseCrop: false
    property bool exportIncludeMarkers: true
    property bool exportIncludeInfo: true
    property real exportCropX0: 0.0
    property real exportCropY0: 0.0
    property real exportCropX1: 1.0
    property real exportCropY1: 1.0

    ListModel { id: csvMarkersModel }
    ListModel { id: spectrumCursorModel }
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

    function spectrumCount() {
        return replaySpectrumModel.count > 0 ? replaySpectrumModel.count : 475
    }
    function clamp01(v) {
        if (v < 0) return 0
        if (v > 1) return 1
        return v
    }

    function csvZoomOffsetX() {
        var w = csvWaterfallViewport ? csvWaterfallViewport.width : 0
        var x = -csvZoomCx * (csvZoomX - 1) * w
        var minX = w - w * csvZoomX
        if (x < minX) x = minX
        if (x > 0) x = 0
        return x
    }

    function csvZoomOffsetY() {
        var h = csvWaterfallViewport ? csvWaterfallViewport.height : 0
        var y = -csvZoomCy * (csvZoomY - 1) * h
        var minY = h - h * csvZoomY
        if (y < minY) y = minY
        if (y > 0) y = 0
        return y
    }

    function resetCsvZoom() {
        csvZoomX = 1.0
        csvZoomY = 1.0
        csvZoomCx = 0.5
        csvZoomCy = 0.5
    }

    function setZoomFromRect(nx0, ny0, nx1, ny1) {
        var x0 = Math.min(nx0, nx1)
        var x1 = Math.max(nx0, nx1)
        var y0 = Math.min(ny0, ny1)
        var y1 = Math.max(ny0, ny1)
        var w = x1 - x0
        var h = y1 - y0
        if (w < 0.01 || h < 0.01) return
        var zx = 1.0 / w
        var zy = 1.0 / h
        if (zx < csvZoomMin) zx = csvZoomMin
        if (zy < csvZoomMin) zy = csvZoomMin
        if (zx > csvZoomMax) zx = csvZoomMax
        if (zy > csvZoomMax) zy = csvZoomMax
        csvZoomX = zx
        csvZoomY = zy
        csvZoomCx = (x0 + x1) * 0.5
        csvZoomCy = (y0 + y1) * 0.5
    }

    function screenToNorm(mx, my) {
        var w = csvWaterfallViewport ? csvWaterfallViewport.width : 0
        var h = csvWaterfallViewport ? csvWaterfallViewport.height : 0
        var nx = (mx - csvZoomOffsetX()) / (w * csvZoomX)
        var ny = (my - csvZoomOffsetY()) / (h * csvZoomY)
        return { x: clamp01(nx), y: clamp01(ny) }
    }

    function mapZoomX(xr) {
        var w = csvWaterfallViewport ? csvWaterfallViewport.width : 0
        return xr * w * csvZoomX + csvZoomOffsetX()
    }

    function mapZoomY(yr) {
        var h = csvWaterfallViewport ? csvWaterfallViewport.height : 0
        return yr * h * csvZoomY + csvZoomOffsetY()
    }

    function cursorIndex(xNorm) {
        return Math.round(xNorm * (spectrumCount() - 1))
    }

    function cursorDbm(xNorm) {
        return replaySpectrumModel.valueAt(cursorIndex(xNorm))
    }

    function cursorFreq(xNorm) {
        return csvFreqMin + xNorm * (csvFreqMax - csvFreqMin)
    }

    function addSpectrumCursor() {
        if (spectrumCursorModel.count >= maxSpectrumCursors) return
        var x = spectrumCursorModel.count === 0 ? 0.35 : 0.65
        spectrumCursorModel.append({ xNorm: x })
    }

    function removeSpectrumCursor() {
        if (spectrumCursorModel.count > 0) {
            spectrumCursorModel.remove(spectrumCursorModel.count - 1)
        }
    }

    function resetExportCrop() {
        exportCropX0 = 0.0
        exportCropY0 = 0.0
        exportCropX1 = 1.0
        exportCropY1 = 1.0
    }

    function exportMarkersForImage() {
        var out = []
        for (var i = 0; i < csvMarkersModel.count; ++i) {
            var m = csvMarkersModel.get(i)
            var marker = {
                xNorm: Number(m.xNorm),
                frameIndex: Number(m.frameIndex),
                color: m.color ? String(m.color) : "#00ff66"
            }
            if (m.freq !== undefined) marker.freq = Number(m.freq)
            if (m.dbm !== undefined) marker.dbm = Number(m.dbm)
            if (m.time !== undefined) marker.time = String(m.time)
            out.push(marker)
        }
        return out
    }

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
                                onHeightChanged: if (model) model.setHeight(Math.max(1, Math.round(height)))
                                Component.onCompleted: if (model) model.setHeight(Math.max(1, Math.round(height)))
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
                    Button {
                        text: "Jump to Max"
                        enabled: csvReplay.loaded
                        onClicked: {
                            if (!csvReplay.loaded) return
                            var maxIndex = csvReplay.findMaxSignalIndex()
                            if (maxIndex >= 0) {
                                csvReplay.setIndex(maxIndex)
                            }
                        }
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

                Label { text: csvReplay.lastError; visible: csvReplay.lastError.length > 0; color: "#ff6666" }
                Label { text: csvReplay.lastExportStatus; visible: csvReplay.lastExportStatus.length > 0; color: "#8fd18f" }

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
                                    Item {
                                        id: csvSpectrumArea
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true

                                        SpectrumItem {
                                            id: csvSpectrumDisplay
                                            anchors.fill: parent
                                            model: replaySpectrumModel
                                        }

                                        Repeater {
                                            model: spectrumCursorModel
                                              delegate: Item {
                                                  anchors.fill: parent
                                                  property real xNorm: model.xNorm
                                                  property int idx: cursorIndex(xNorm)
                                                  property real valueDbm: cursorDbm(xNorm)
                                                  property real yNorm: (csvDbmMax - csvDbmMin) > 0.001 ? (valueDbm - csvDbmMin) / (csvDbmMax - csvDbmMin) : 0.5
                                                  property real xPos: xNorm * width
                                                  property real yPos: (1.0 - Math.max(0.0, Math.min(1.0, yNorm))) * height
                                                  property color cursorColor: index === 0 ? "#ffb000" : "#4db6ff"

                                                  Rectangle {
                                                      x: xPos
                                                      y: 0
                                                      width: 1
                                                      height: parent.height
                                                      color: cursorColor
                                                      opacity: 0.6
                                                  }

                                                  Shape {
                                                      id: cursorMarker
                                                      x: xPos - width / 2
                                                      y: yPos - height
                                                      width: 12
                                                      height: 10
                                                      ShapePath {
                                                          strokeWidth: 1
                                                          strokeColor: "#000000"
                                                          fillColor: cursorColor
                                                          startX: 0
                                                          startY: 0
                                                          PathLine { x: cursorMarker.width; y: 0 }
                                                          PathLine { x: cursorMarker.width / 2; y: cursorMarker.height }
                                                          PathLine { x: 0; y: 0 }
                                                      }
                                                  }

                                                  MouseArea {
                                                      anchors.fill: cursorMarker
                                                      cursorShape: Qt.SizeHorCursor
                                                      onPositionChanged: {
                                                          if (!pressed) return
                                                          var p = mapToItem(csvSpectrumArea, mouse.x, mouse.y)
                                                          var nx = p.x / csvSpectrumArea.width
                                                        if (nx < 0) nx = 0
                                                        if (nx > 1) nx = 1
                                                        spectrumCursorModel.setProperty(index, "xNorm", nx)
                                                    }
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
                                        id: csvWaterfallViewport
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        clip: true
                                    
                                        WaterfallItem {
                                            id: csvWaterfallDisplay
                                            width: parent.width
                                            height: parent.height
                                            model: replayWaterfallModel
                                            transform: Scale { origin.x: 0; origin.y: 0; xScale: csvZoomX; yScale: csvZoomY }
                                            x: csvZoomOffsetX()
                                            y: csvZoomOffsetY()
                                            onHeightChanged: {
                                                var h = Math.max(1, Math.round(height))
                                                if (model) model.setHeight(h)
                                                csvReplay.setWaterfallDepth(h)
                                            }
                                            Component.onCompleted: {
                                                var h = Math.max(1, Math.round(height))
                                                if (model) model.setHeight(h)
                                                csvReplay.setWaterfallDepth(h)
                                            }
                                        }
                                    
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
                                    
                                        Rectangle {
                                            id: zoomRect
                                            visible: zoomArea.zoomSelecting
                                            x: Math.min(zoomArea.selStartX, zoomArea.selEndX)
                                            y: Math.min(zoomArea.selStartY, zoomArea.selEndY)
                                            width: Math.abs(zoomArea.selEndX - zoomArea.selStartX)
                                            height: Math.abs(zoomArea.selEndY - zoomArea.selStartY)
                                            color: "#00ffffff"
                                            border.color: "#ffaa00"
                                            border.width: 1
                                        }

                                        MouseArea {
                                            id: zoomArea
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: csvZoomMode ? Qt.CrossCursor : Qt.ArrowCursor
                                            property bool zoomSelecting: false
                                            property real selStartX: 0
                                            property real selStartY: 0
                                            property real selEndX: 0
                                            property real selEndY: 0

                                            onPressed: function(mouse) {
                                                if (!csvZoomMode) return
                                                zoomSelecting = true
                                                selStartX = mouse.x
                                                selStartY = mouse.y
                                                selEndX = mouse.x
                                                selEndY = mouse.y
                                            }
                                            onPositionChanged: function(mouse) {
                                                if (!zoomSelecting) return
                                                selEndX = mouse.x
                                                selEndY = mouse.y
                                            }
                                            onReleased: function(mouse) {
                                                if (!zoomSelecting) return
                                                zoomSelecting = false
                                                var dx = Math.abs(selEndX - selStartX)
                                                var dy = Math.abs(selEndY - selStartY)
                                                if (dx < 4 || dy < 4) return
                                                var left = Math.min(selStartX, selEndX)
                                                var right = Math.max(selStartX, selEndX)
                                                var top = Math.min(selStartY, selEndY)
                                                var bottom = Math.max(selStartY, selEndY)
                                                var n0 = screenToNorm(left, top)
                                                var n1 = screenToNorm(right, bottom)
                                                setZoomFromRect(n0.x, n0.y, n1.x, n1.y)
                                            }
                                            onClicked: function(mouse) {
                                                if (csvZoomMode || !csvMarkersEnabled || !csvReplay.loaded) return
                                                var n = screenToNorm(mouse.x, mouse.y)
                                                var row = Math.round(n.y * (replayWaterfallModel.height - 1))
                                                var frameIndex = csvReplay.currentIndex - row
                                                if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
                                                var xIdx = Math.round(n.x * (replayWaterfallModel.width - 1))
                                                var freq = csvFreqMin + n.x * (csvFreqMax - csvFreqMin)
                                                var dbm = replayWaterfallModel.valueAt(xIdx, row)
                                                var timeText = csvReplay.timestampAt(frameIndex)
                                                csvMarkersModel.append({ xNorm: n.x, frameIndex: frameIndex, color: csvNextMarkerColor, freq: freq, dbm: dbm, time: timeText })
                                            }
                                        }
                                    
                                        Repeater {
                                            model: csvMarkersModel
                                            delegate: Item {
                                                anchors.fill: parent
                                                property int row: csvReplay.currentIndex - model.frameIndex
                                                property bool inView: row >= 0 && row < replayWaterfallModel.height
                                                visible: inView
                                                property real yNorm: replayWaterfallModel.height > 1 ? (row / (replayWaterfallModel.height - 1)) : 0
                                                property real px: mapZoomX(model.xNorm)
                                                property real py: mapZoomY(yNorm)
                                                property real freq: model.freq !== undefined ? model.freq : (csvFreqMin + model.xNorm * (csvFreqMax - csvFreqMin))
                                                property int xIdx: Math.round(model.xNorm * (replayWaterfallModel.width - 1))
                                                property real dbm: model.dbm !== undefined ? model.dbm : (inView ? replayWaterfallModel.valueAt(xIdx, row) : 0)
                                                property string timeText: model.time !== undefined ? model.time : (csvReplay.loaded ? csvReplay.timestampAt(model.frameIndex) : "")
                                                property string markerColor: model.color ? model.color : "#00ff66"
                                                Rectangle { x: px - 5; y: py - 1; width: 11; height: 2; color: markerColor }
                                                Rectangle { x: px - 1; y: py - 5; width: 2; height: 11; color: markerColor }
                                                Rectangle {
                                                    id: markerLabelBg
                                                    width: markerLabel.implicitWidth + 8
                                                    height: markerLabel.implicitHeight + 4
                                                    x: px + (px > parent.width * 0.6 ? -width - 6 : 6)
                                                    y: py + (py > parent.height * 0.6 ? -height - 6 : 6)
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: markerColor
                                                    radius: 3
                                                    Text { id: markerLabel; anchors.centerIn: parent; text: freq.toFixed(6) + " MHz\n" + dbm.toFixed(1) + " dBm\n" + timeText; color: "white"; font.pixelSize: 9 }
                                                }
                                                MouseArea {
                                                    anchors.fill: markerLabelBg
                                                    acceptedButtons: Qt.RightButton
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            csvMarkersModel.remove(index)
                                                        }
                                                    }
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

                        ScrollView {
                            anchors.fill: parent
                            anchors.margins: 8
                            ScrollBar.vertical.policy: ScrollBar.AlwaysOn
                            clip: true

                            ColumnLayout {
                                id: csvMenuContent
                                width: parent.width
                                spacing: 10

                                GroupBox {
                                    title: "Info"
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 4
                                        Label { text: "Start: " + (csvReplay.loaded ? csvReplay.timestampAt(0) : "--") }
                                        Label { text: "End:   " + (csvReplay.loaded ? csvReplay.timestampAt(csvReplay.lineCount - 1) : "--") }
                                        Label { text: "Center: " + csvCenterFreq.toFixed(6) + " MHz" }
                                        Label { text: "Span:   " + csvSpanKhz.toFixed(2) + " kHz" }
                                        Label { text: "Gain Min: " + (csvReplay.loaded ? csvReplay.fileMinDbm.toFixed(1) : "--") + " dBm" }
                                        Label { text: "Gain Max: " + (csvReplay.loaded ? csvReplay.fileMaxDbm.toFixed(1) : "--") + " dBm" }
                                        Label { text: "Gain Avg: " + (csvReplay.loaded ? csvReplay.fileAvgDbm.toFixed(1) : "--") + " dBm" }
                                    }
                                }

                                GroupBox {
                                    title: "Spectre"
                                    Layout.fillWidth: true

                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 6

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Button {
                                                text: "+"
                                                enabled: spectrumCursorModel.count < maxSpectrumCursors
                                                onClicked: addSpectrumCursor()
                                            }
                                            Button {
                                                text: "-"
                                                enabled: spectrumCursorModel.count > 0
                                                onClicked: removeSpectrumCursor()
                                            }
                                            Label {
                                                text: spectrumCursorModel.count + "/" + maxSpectrumCursors
                                            }
                                        }

                                        Repeater {
                                            model: spectrumCursorModel
                                            delegate: ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Label {
                                                    text: "C" + (index + 1) +
                                                          "  F=" + cursorFreq(model.xNorm).toFixed(6) + " MHz" +
                                                          "  P=" + cursorDbm(model.xNorm).toFixed(1) + " dBm"
                                                    font.pixelSize: 10
                                                }
                                            }
                                        }

                                        Label {
                                            visible: spectrumCursorModel.count >= 2
                                            text: spectrumCursorModel.count >= 2
                                                  ? ("Delta F=" + Math.abs(cursorFreq(spectrumCursorModel.get(1).xNorm) - cursorFreq(spectrumCursorModel.get(0).xNorm)).toFixed(6) + " MHz" +
                                                     "  Delta P=" + Math.abs(cursorDbm(spectrumCursorModel.get(1).xNorm) - cursorDbm(spectrumCursorModel.get(0).xNorm)).toFixed(1) + " dB")
                                                  : ""
                                            font.pixelSize: 10
                                        }
                                    }
                                }

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
                                    title: "Zoom"
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 6
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Button {
                                                text: csvZoomMode ? "Zoom: ON" : "Zoom"
                                                checkable: true
                                                checked: csvZoomMode
                                                onClicked: csvZoomMode = checked
                                            }
                                            Button {
                                                text: "Reset"
                                                onClicked: {
                                                    resetCsvZoom()
                                                    csvZoomMode = false
                                                }
                                            }
                                        }
                                        Label { text: "Drag a rectangle in waterfall to zoom"; font.pixelSize: 10 }
                                        Label { text: "Esc to exit zoom mode"; font.pixelSize: 10 }
                                    }
                                }

                                GroupBox {
                                    title: "Markers"
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 6
                                        CheckBox { text: csvMarkersEnabled ? "Markers ON" : "Markers OFF"; checked: csvMarkersEnabled; onToggled: csvMarkersEnabled = checked }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Repeater {
                                                model: csvMarkerColors
                                                delegate: Rectangle {
                                                    width: 16
                                                    height: 16
                                                    radius: 3
                                                    color: modelData
                                                    border.color: csvNextMarkerColor === modelData ? "#ffffff" : "#2a2a2a"
                                                    border.width: csvNextMarkerColor === modelData ? 2 : 1
                                                    MouseArea {
                                                        anchors.fill: parent
                                                        onClicked: csvNextMarkerColor = modelData
                                                    }
                                                }
                                            }
                                        }
                                        Button { text: "Clear markers"; onClicked: csvMarkersModel.clear() }
                                    }
                                }

                                GroupBox {
                                    title: "Export"
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 6
                                        Button {
                                            text: "Exporter metadata (.json)"
                                            enabled: csvReplay.loaded
                                            onClicked: csvMetadataDialog.open()
                                        }
                                        Button {
                                            text: "Exporter image"
                                            enabled: csvReplay.loaded
                                            onClicked: {
                                                resetExportCrop()
                                                csvReplay.generateExportPreview(replaySpectrumModel.dbmMin, replaySpectrumModel.dbmMax, 1200, 900)
                                                exportPreviewDialog.open()
                                            }
                                        }
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

    FileDialog {
        id: csvMetadataDialog
        title: "Exporter metadata JSON"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        nameFilters: ["JSON files (*.json)", "All files (*)"]
        onAccepted: csvReplay.exportMetadataJson(selectedFile)
    }

    FileDialog {
        id: csvExportDialog
        title: "Exporter waterfall"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "png"
        nameFilters: ["PNG image (*.png)", "JPEG image (*.jpg *.jpeg)"]
        onAccepted: {
            var markers = exportMarkersForImage()
            if (csvExportUseCrop) {
                csvReplay.exportWaterfallImageCropWithMarkers(
                    selectedFile,
                    replaySpectrumModel.dbmMin,
                    replaySpectrumModel.dbmMax,
                    exportCropX0, exportCropY0, exportCropX1, exportCropY1,
                    markers, exportIncludeMarkers,
                    exportIncludeInfo, csvCenterFreq,
                    (csvReplay.loaded ? (csvReplay.timestampAt(0) + " -> " + csvReplay.timestampAt(csvReplay.lineCount - 1)) : "--")
                )
            } else {
                csvReplay.exportWaterfallImageWithMarkers(
                    selectedFile,
                    replaySpectrumModel.dbmMin,
                    replaySpectrumModel.dbmMax,
                    markers, exportIncludeMarkers,
                    exportIncludeInfo, csvCenterFreq,
                    (csvReplay.loaded ? (csvReplay.timestampAt(0) + " -> " + csvReplay.timestampAt(csvReplay.lineCount - 1)) : "--")
                )
            }
        }
    }

    Dialog {
        id: exportPreviewDialog
        title: "Apercu export"
        modal: true
        width: Math.max(640, Math.min(900, (parent && parent.width > 0) ? parent.width - 40 : 900))
        height: Math.max(420, Math.min(620, (parent && parent.height > 0) ? parent.height - 40 : 620))
        padding: 10
        standardButtons: Dialog.NoButton

        property bool selecting: false
        property real sx: 0
        property real sy: 0
        property real ex: 0
        property real ey: 0

        contentItem: ColumnLayout {
            spacing: 8

            Label {
                Layout.fillWidth: true
                text: "Image source: " + csvReplay.exportImageWidth + "x" + csvReplay.exportImageHeight
                font.pixelSize: 10
            }
            Label {
                Layout.fillWidth: true
                text: "Selection rectangle: couper lignes (haut/bas) et colonnes (gauche/droite)."
                font.pixelSize: 10
            }
            CheckBox {
                id: exportMarkersCheck
                Layout.fillWidth: true
                text: "Markers"
                checked: exportIncludeMarkers
                onToggled: exportIncludeMarkers = checked
            }
            CheckBox {
                id: exportInfoCheck
                Layout.fillWidth: true
                text: "Infos (Fc + Time)"
                checked: exportIncludeInfo
                onToggled: exportIncludeInfo = checked
            }

            Item {
                id: previewContainer
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 220
                clip: true

                Rectangle {
                    anchors.fill: parent
                    color: "#101820"
                    border.color: "#2a2a2a"
                    radius: 4
                }

                Flickable {
                    id: previewFlick
                    anchors.fill: parent
                    clip: true
                    contentWidth: previewSurface.width
                    contentHeight: previewSurface.height
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {}
                    ScrollBar.horizontal: ScrollBar {}

                    Item {
                        id: previewSurface
                        width: Math.max(1, csvReplay.exportImageWidth)
                        height: Math.max(1, csvReplay.exportImageHeight)

                        Image {
                            id: previewImage
                            anchors.fill: parent
                            source: csvReplay.exportPreviewPath
                            cache: false
                            fillMode: Image.Stretch
                        }

                        Repeater {
                            model: csvMarkersModel
                            delegate: Item {
                                anchors.fill: parent
                                property bool canDraw: exportIncludeMarkers && csvReplay.lineCount > 0 && model.frameIndex >= 0 && model.frameIndex < csvReplay.lineCount
                                visible: canDraw
                                property real px: model.xNorm * previewSurface.width
                                property real py: csvReplay.lineCount > 1
                                                  ? (1.0 - (model.frameIndex / (csvReplay.lineCount - 1))) * previewSurface.height
                                                  : (previewSurface.height * 0.5)
                                property real freq: model.freq !== undefined ? model.freq : (csvFreqMin + model.xNorm * (csvFreqMax - csvFreqMin))
                                property real dbm: model.dbm !== undefined ? model.dbm : 0
                                property string timeText: model.time !== undefined ? model.time : ""
                                property string markerColor: model.color ? model.color : "#00ff66"
                                Rectangle { x: px - 5; y: py - 1; width: 11; height: 2; color: markerColor }
                                Rectangle { x: px - 1; y: py - 5; width: 2; height: 11; color: markerColor }
                                Rectangle {
                                    id: previewMarkerLabelBg
                                    width: previewMarkerLabel.implicitWidth + 8
                                    height: previewMarkerLabel.implicitHeight + 4
                                    x: px + (px > previewSurface.width * 0.6 ? -width - 6 : 6)
                                    y: py + (py > previewSurface.height * 0.6 ? -height - 6 : 6)
                                    color: "#000000"
                                    opacity: 0.75
                                    border.color: markerColor
                                    radius: 3
                                    Text {
                                        id: previewMarkerLabel
                                        anchors.centerIn: parent
                                        text: freq.toFixed(6) + " MHz\n" + dbm.toFixed(1) + " dBm\n" + timeText
                                        color: "white"
                                        font.pixelSize: 9
                                    }
                                }
                            }
                        }

                        Rectangle {
                            id: exportInfoOverlay
                            visible: exportIncludeInfo
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 24
                            color: "#bf000000"
                            border.color: "#ffffff"
                            border.width: 1
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.right: parent.right
                                anchors.rightMargin: 8
                                color: "white"
                                font.pixelSize: 13
                                elide: Text.ElideRight
                                text: "Fc: " + csvCenterFreq.toFixed(6) + " MHz    Time: " +
                                      (csvReplay.loaded ? (csvReplay.timestampAt(0) + " -> " + csvReplay.timestampAt(csvReplay.lineCount - 1)) : "--")
                            }
                        }

                        Rectangle {
                            id: exportSelection
                            visible: exportPreviewDialog.selecting || exportCropX0 > 0.0 || exportCropY0 > 0.0 || exportCropX1 < 1.0 || exportCropY1 < 1.0
                            x: exportPreviewDialog.selecting ? Math.min(exportPreviewDialog.sx, exportPreviewDialog.ex) : exportCropX0 * previewSurface.width
                            y: exportPreviewDialog.selecting ? Math.min(exportPreviewDialog.sy, exportPreviewDialog.ey) : exportCropY0 * previewSurface.height
                            width: exportPreviewDialog.selecting ? Math.abs(exportPreviewDialog.ex - exportPreviewDialog.sx) : (exportCropX1 - exportCropX0) * previewSurface.width
                            height: exportPreviewDialog.selecting ? Math.abs(exportPreviewDialog.ey - exportPreviewDialog.sy) : (exportCropY1 - exportCropY0) * previewSurface.height
                            color: "#33ffffff"
                            border.color: "#00ff66"
                            border.width: 1
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: csvReplay.exportPreviewPath.length > 0
                            onPressed: function(mouse) {
                                exportPreviewDialog.selecting = true
                                exportPreviewDialog.sx = mouse.x
                                exportPreviewDialog.sy = mouse.y
                                exportPreviewDialog.ex = mouse.x
                                exportPreviewDialog.ey = mouse.y
                            }
                            onPositionChanged: function(mouse) {
                                if (!exportPreviewDialog.selecting) return
                                exportPreviewDialog.ex = Math.max(0, Math.min(width, mouse.x))
                                exportPreviewDialog.ey = Math.max(0, Math.min(height, mouse.y))
                            }
                            onReleased: function(mouse) {
                                if (!exportPreviewDialog.selecting) return
                                exportPreviewDialog.selecting = false
                                exportPreviewDialog.ex = Math.max(0, Math.min(width, mouse.x))
                                exportPreviewDialog.ey = Math.max(0, Math.min(height, mouse.y))

                                var left = Math.min(exportPreviewDialog.sx, exportPreviewDialog.ex)
                                var right = Math.max(exportPreviewDialog.sx, exportPreviewDialog.ex)
                                var top = Math.min(exportPreviewDialog.sy, exportPreviewDialog.ey)
                                var bottom = Math.max(exportPreviewDialog.sy, exportPreviewDialog.ey)
                                if ((right - left) > 4 && (bottom - top) > 4) {
                                    exportCropX0 = left / width
                                    exportCropX1 = right / width
                                    exportCropY0 = top / height
                                    exportCropY1 = bottom / height
                                } else {
                                    resetExportCrop()
                                }
                            }
                        }
                    }
                }
            }
        }

        footer: Rectangle {
            implicitHeight: 56
            color: "#f2f2f2"
            border.color: "#d0d0d0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8

                Button {
                    text: "Reset zone"
                    onClicked: {
                        resetExportCrop()
                        exportPreviewDialog.selecting = false
                    }
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: "Exporter complet"
                    enabled: csvReplay.loaded
                    onClicked: {
                        csvExportUseCrop = false
                        csvExportDialog.open()
                    }
                }

                Button {
                    text: "Exporter zone"
                    enabled: csvReplay.loaded
                    onClicked: {
                        csvExportUseCrop = true
                        csvExportDialog.open()
                    }
                }

                Button {
                    text: "Fermer"
                    onClicked: exportPreviewDialog.close()
                }
            }
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
}
