import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQml
import IC705

Window {
    id: root
    width: 1000
    height: 600
    visible: true
    title: "IC705 Qt - Step 1"

    Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.onPressed: {
            if (event.key === Qt.Key_Escape && handleGlobalEscape()) {
                event.accepted = true
            } else if ((event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) && removeSelectedCsvObject()) {
                event.accepted = true
            } else if (event.key === Qt.Key_Z && (event.modifiers & Qt.ControlModifier) && undoLastCsvAction()) {
                event.accepted = true
            }
        }
    }

    Shortcut {
        sequence: "Esc"
        context: Qt.ApplicationShortcut
        onActivated: handleGlobalEscape()
    }
    Shortcut {
        sequence: "Del"
        context: Qt.ApplicationShortcut
        onActivated: removeSelectedCsvObject()
    }
    Shortcut {
        sequence: "Backspace"
        context: Qt.ApplicationShortcut
        onActivated: removeSelectedCsvObject()
    }
    Shortcut {
        sequence: "Ctrl+Z"
        context: Qt.ApplicationShortcut
        onActivated: undoLastCsvAction()
    }

    property real defaultFreq: 7.1
    property real defaultSpanKhz: 5.0
    property var liveSpanOptionsKhz: [2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0]
    property int liveRfGain: 0

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
    property string csvWfTopTime: csvReplay.loaded ? shortTimestampLabel(csvReplay.currentTimestamp) : "--"
    property string csvWfBottomTime: csvReplay.loaded ? shortTimestampLabel(csvReplay.timestampAt(wfBottomIndex)) : "--"
    property bool csvMarkersEnabled: false
    property string csvToolMode: "mouse"
    property string csvNextMarkerColor: "#00ff66"
    property var csvMarkerColors: ["#00ff66", "#ff9900", "#00aaff", "#ff3366", "#ffffff"]
    property int maxSpectrumCursors: 2
    property int csvMarkerSelectedIndex: -1
    property bool csvMeasureMode: false
    property bool csvMeasurePending: false
    property int csvMeasureSelectedIndex: -1
    property real csvMeasureStartXNorm: 0.5
    property real csvMeasureStartYNorm: 0.5
    property real csvMeasureHoverYNorm: 0.5
    property int csvMeasureStartFrameIndex: -1
    property string csvMeasureStartTime: ""
    property int csvMeasureHoverFrameIndex: -1
    property string csvMeasureHoverTime: ""
    property bool csvMeasureFMode: false
    property bool csvMeasureFPending: false
    property int csvMeasureFSelectedIndex: -1
    property real csvMeasureFStartXNorm: 0.5
    property real csvMeasureFStartYNorm: 0.5
    property real csvMeasureFHoverXNorm: 0.5
    property int csvMeasureFStartFrameIndex: -1
    property bool csvMeasureTFMode: false
    property bool csvMeasureTFPending: false
    property int csvMeasureTFSelectedIndex: -1
    property real csvMeasureTFStartXNorm: 0.5
    property real csvMeasureTFStartYNorm: 0.5
    property real csvMeasureTFHoverXNorm: 0.5
    property real csvMeasureTFHoverYNorm: 0.5
    property int csvMeasureTFStartFrameIndex: -1
    property string csvMeasureTFStartTime: ""
    property int csvMeasureTFHoverFrameIndex: -1
    property string csvMeasureTFHoverTime: ""
    property var csvUndoStack: []
    property int csvUndoMaxDepth: 60

    property string defaultRadioIp: "192.168.59.1"
    property string defaultRadioUser: "IC-705-7"
    property string defaultRadioPass: "bouter20xx"
    property string defaultRadioName: "IC-705-7"
    property string defaultRadioMac: "00:90:C7:13:CA:75"
    property string liveFreqUnit: "MHz"

    property string csvPath: ""
    property bool csvExportUseCrop: false
    property bool exportIncludeMarkers: true
    property bool exportIncludeInfo: true
    property bool exportIncludeFreqAxis: false
    property bool exportIncludeTimeAxis: false
    property real exportCropX0: 0.0
    property real exportCropY0: 0.0
    property real exportCropX1: 1.0
    property real exportCropY1: 1.0

    ListModel { id: csvMarkersModel }
    ListModel { id: spectrumCursorModel }
    ListModel { id: csvMeasureModel }
    ListModel { id: csvMeasureFModel }
    ListModel { id: csvMeasureTFModel }
    Connections {
        target: csvReplay
        function onLoadedChanged() {
            if (csvReplay.loaded) {
                csvMarkersModel.clear()
                csvMeasureModel.clear()
                csvMeasureFModel.clear()
                csvMeasureTFModel.clear()
                csvUndoStack = []
                csvMeasurePending = false
                csvMeasureFPending = false
                csvMeasureTFPending = false
                root.csvMarkerSelectedIndex = -1
                root.csvMeasureSelectedIndex = -1
                root.csvMeasureFSelectedIndex = -1
                root.csvMeasureTFSelectedIndex = -1
                csvMeasureStartFrameIndex = -1
                csvMeasureStartTime = ""
                csvMeasureHoverFrameIndex = -1
                csvMeasureHoverTime = ""
                csvMeasureStartYNorm = 0.5
                csvMeasureHoverYNorm = 0.5
                csvMeasureFStartXNorm = 0.5
                csvMeasureFStartYNorm = 0.5
                csvMeasureFHoverXNorm = 0.5
                csvMeasureFStartFrameIndex = -1
                csvMeasureTFStartXNorm = 0.5
                csvMeasureTFStartYNorm = 0.5
                csvMeasureTFHoverXNorm = 0.5
                csvMeasureTFHoverYNorm = 0.5
                csvMeasureTFStartFrameIndex = -1
                csvMeasureTFStartTime = ""
                csvMeasureTFHoverFrameIndex = -1
                csvMeasureTFHoverTime = ""
                setCsvTool("mouse")
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

    function clearSelectionCsv() {
        root.csvMarkerSelectedIndex = -1
        root.csvMeasureSelectedIndex = -1
        root.csvMeasureFSelectedIndex = -1
        root.csvMeasureTFSelectedIndex = -1
    }

    function selectMarkerAt(idx) {
        root.csvMarkerSelectedIndex = idx
        root.csvMeasureSelectedIndex = -1
        root.csvMeasureFSelectedIndex = -1
        root.csvMeasureTFSelectedIndex = -1
    }

    function selectMeasureTAt(idx) {
        root.csvMarkerSelectedIndex = -1
        root.csvMeasureSelectedIndex = idx
        root.csvMeasureFSelectedIndex = -1
        root.csvMeasureTFSelectedIndex = -1
    }

    function selectMeasureFAt(idx) {
        root.csvMarkerSelectedIndex = -1
        root.csvMeasureSelectedIndex = -1
        root.csvMeasureFSelectedIndex = idx
        root.csvMeasureTFSelectedIndex = -1
    }

    function selectMeasureTFAt(idx) {
        root.csvMarkerSelectedIndex = -1
        root.csvMeasureSelectedIndex = -1
        root.csvMeasureFSelectedIndex = -1
        root.csvMeasureTFSelectedIndex = idx
    }

    function cloneModelData(model) {
        var out = []
        for (var i = 0; i < model.count; ++i) {
            var src = model.get(i)
            var dst = {}
            for (var k in src) dst[k] = src[k]
            out.push(dst)
        }
        return out
    }

    function restoreModelData(model, data) {
        model.clear()
        for (var i = 0; i < data.length; ++i) model.append(data[i])
    }

    function pushCsvUndoSnapshot(reason) {
        var snapshot = {
            reason: reason,
            markers: cloneModelData(csvMarkersModel),
            measuresT: cloneModelData(csvMeasureModel),
            measuresF: cloneModelData(csvMeasureFModel),
            measuresTF: cloneModelData(csvMeasureTFModel),
            markerSel: root.csvMarkerSelectedIndex,
            tSel: root.csvMeasureSelectedIndex,
            fSel: root.csvMeasureFSelectedIndex,
            tfSel: root.csvMeasureTFSelectedIndex
        }
        root.csvUndoStack.push(snapshot)
        if (root.csvUndoStack.length > root.csvUndoMaxDepth) root.csvUndoStack.shift()
    }

    function undoLastCsvAction() {
        if (root.csvUndoStack.length <= 0) return false
        var s = root.csvUndoStack.pop()
        restoreModelData(csvMarkersModel, s.markers || [])
        restoreModelData(csvMeasureModel, s.measuresT || [])
        restoreModelData(csvMeasureFModel, s.measuresF || [])
        restoreModelData(csvMeasureTFModel, s.measuresTF || [])
        root.csvMarkerSelectedIndex = (s.markerSel !== undefined) ? s.markerSel : -1
        root.csvMeasureSelectedIndex = (s.tSel !== undefined) ? s.tSel : -1
        root.csvMeasureFSelectedIndex = (s.fSel !== undefined) ? s.fSel : -1
        root.csvMeasureTFSelectedIndex = (s.tfSel !== undefined) ? s.tfSel : -1
        clearPendingMeasure()
        return true
    }

    function removeSelectedCsvObject() {
        if (root.csvToolMode !== "mouse") return false
        if (root.csvMarkerSelectedIndex >= 0 && root.csvMarkerSelectedIndex < csvMarkersModel.count) {
            pushCsvUndoSnapshot("delete marker")
            csvMarkersModel.remove(root.csvMarkerSelectedIndex)
            root.csvMarkerSelectedIndex = -1
            return true
        }
        if (root.csvMeasureSelectedIndex >= 0 && root.csvMeasureSelectedIndex < csvMeasureModel.count) {
            pushCsvUndoSnapshot("delete measure T")
            csvMeasureModel.remove(root.csvMeasureSelectedIndex)
            root.csvMeasureSelectedIndex = -1
            return true
        }
        if (root.csvMeasureFSelectedIndex >= 0 && root.csvMeasureFSelectedIndex < csvMeasureFModel.count) {
            pushCsvUndoSnapshot("delete measure F")
            csvMeasureFModel.remove(root.csvMeasureFSelectedIndex)
            root.csvMeasureFSelectedIndex = -1
            return true
        }
        if (root.csvMeasureTFSelectedIndex >= 0 && root.csvMeasureTFSelectedIndex < csvMeasureTFModel.count) {
            pushCsvUndoSnapshot("delete measure TF")
            csvMeasureTFModel.remove(root.csvMeasureTFSelectedIndex)
            root.csvMeasureTFSelectedIndex = -1
            return true
        }
        return false
    }

    function csvActiveToolLabel() {
        if (csvToolMode === "zoom") return "Zoom"
        if (csvToolMode === "measureTF") return "\u0394T/\u0394F"
        if (csvToolMode === "measureT") return "\u0394T"
        if (csvToolMode === "measureF") return "\u0394F"
        if (csvToolMode === "marker") return "Marker"
        return "Souris"
    }

    function setCsvTool(mode) {
        var nextMode = mode
        if (nextMode !== "mouse" && nextMode !== "marker" &&
                nextMode !== "measureT" && nextMode !== "measureF" &&
                nextMode !== "measureTF" && nextMode !== "zoom") {
            nextMode = "mouse"
        }
        if (csvToolMode === nextMode) return
        csvToolMode = nextMode
        csvMarkersEnabled = (nextMode === "marker")
        csvMeasureMode = (nextMode === "measureT")
        csvMeasureFMode = (nextMode === "measureF")
        csvMeasureTFMode = (nextMode === "measureTF")
        csvZoomMode = (nextMode === "zoom")
        clearPendingMeasure()
    }

    function handleGlobalEscape() {
        if (csvToolMode !== "mouse") {
            setCsvTool("mouse")
            return true
        }
        if (csvMeasurePending || csvMeasureFPending || csvMeasureTFPending) {
            clearPendingMeasure()
            return true
        }
        if (csvMarkerSelectedIndex >= 0 || csvMeasureSelectedIndex >= 0 || csvMeasureFSelectedIndex >= 0 || csvMeasureTFSelectedIndex >= 0) {
            clearSelectionCsv()
            return true
        }
        return false
    }

    function applyLiveFrequencyEdit() {
        var raw = (liveFreqField.text || "").trim().replace(/,/g, ".")
        var value = Number(raw)
        if (!isFinite(value) || value <= 0.0) {
            liveFreqField.text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
            return
        }
        var valueMHz = toMHz(value, liveFreqUnit)
        if (!isFinite(valueMHz) || valueMHz <= 0.0) {
            liveFreqField.text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
            return
        }
        if (!civClient.setFrequencyMHz(valueMHz)) {
            return
        }
        liveFreqField.text = formatLiveFrequencyForUnit(valueMHz, liveFreqUnit)
    }

    function toMHz(value, unitText) {
        if (unitText === "Hz") return value / 1000000.0
        if (unitText === "kHz") return value / 1000.0
        return value
    }

    function fromMHz(valueMHz, unitText) {
        if (unitText === "Hz") return valueMHz * 1000000.0
        if (unitText === "kHz") return valueMHz * 1000.0
        return valueMHz
    }

    function frequencyDecimals(unitText) {
        if (unitText === "Hz") return 0
        if (unitText === "kHz") return 3
        return 6
    }

    function formatLiveFrequencyForUnit(valueMHz, unitText) {
        if (!(valueMHz > 0.0)) return ""
        var unitValue = fromMHz(valueMHz, unitText)
        return unitValue.toFixed(frequencyDecimals(unitText))
    }

    function spanOptionIndex(spanKhz) {
        var bestIndex = 0
        var bestErr = 1e30
        for (var i = 0; i < liveSpanOptionsKhz.length; ++i) {
            var err = Math.abs(Number(liveSpanOptionsKhz[i]) - spanKhz)
            if (err < bestErr) {
                bestErr = err
                bestIndex = i
            }
        }
        return bestIndex
    }

    function applyLiveSpanSelection() {
        if (liveSpanCombo.currentIndex < 0 || liveSpanCombo.currentIndex >= liveSpanOptionsKhz.length) return
        var spanKhz = Number(liveSpanOptionsKhz[liveSpanCombo.currentIndex])
        if (!isFinite(spanKhz) || spanKhz <= 0) return
        if (!civClient.setScopeSpanKHz(spanKhz)) return
        liveSpanKhz = spanKhz
    }

    function applyLiveRfGain(value) {
        var v = Math.round(Number(value))
        if (!isFinite(v)) return
        if (v < 0) v = 0
        if (v > 255) v = 255
        liveRfGain = v
        civClient.setRfGain(v)
    }

    function resetExportCrop() {
        exportCropX0 = 0.0
        exportCropY0 = 0.0
        exportCropX1 = 1.0
        exportCropY1 = 1.0
    }

    function timestampToMs(text) {
        if (!text || text.length < 10) return NaN
        var iso = text.replace(" ", "T")
        var t = Date.parse(iso)
        return isNaN(t) ? NaN : t
    }

    function shortTimestampLabel(text) {
        if (!text || text.length === 0) return "--"
        var sep = text.indexOf(" ")
        if (sep < 0) sep = text.indexOf("T")
        if (sep >= 0 && sep + 1 < text.length) {
            var tail = text.slice(sep + 1)
            if (tail.endsWith("Z")) tail = tail.slice(0, tail.length - 1)
            var dot = tail.indexOf(".")
            if (dot > 0) tail = tail.slice(0, dot)
            return tail
        }
        return text
    }

    function formatDeltaTimeMs(deltaMs) {
        var ms = Math.max(0, Math.round(deltaMs))
        if (ms < 1000) return ms + " ms"
        var sec = ms / 1000.0
        if (sec < 60) return sec.toFixed(3) + " s"
        var totalSec = Math.floor(sec)
        var mins = Math.floor(totalSec / 60)
        var remSec = totalSec % 60
        return mins + " min " + remSec + " s"
    }

    function formatDeltaFreqMHz(deltaMHz) {
        var v = Math.abs(deltaMHz)
        if (v < 1.0) return (v * 1000.0).toFixed(3) + " kHz"
        return v.toFixed(6) + " MHz"
    }

    function deltaTextFromTimes(startTime, endTime) {
        var t0 = timestampToMs(startTime)
        var t1 = timestampToMs(endTime)
        if (isNaN(t0) || isNaN(t1)) return "--"
        return formatDeltaTimeMs(Math.abs(t1 - t0))
    }

    function clearPendingMeasure() {
        csvMeasurePending = false
        csvMeasureStartFrameIndex = -1
        csvMeasureStartTime = ""
        csvMeasureHoverFrameIndex = -1
        csvMeasureHoverTime = ""
        csvMeasureStartYNorm = 0.5
        csvMeasureHoverYNorm = 0.5
        csvMeasureFPending = false
        csvMeasureFStartXNorm = 0.5
        csvMeasureFStartYNorm = 0.5
        csvMeasureFHoverXNorm = 0.5
        csvMeasureFStartFrameIndex = -1
        csvMeasureTFPending = false
        csvMeasureTFStartXNorm = 0.5
        csvMeasureTFStartYNorm = 0.5
        csvMeasureTFHoverXNorm = 0.5
        csvMeasureTFHoverYNorm = 0.5
        csvMeasureTFStartFrameIndex = -1
        csvMeasureTFStartTime = ""
        csvMeasureTFHoverFrameIndex = -1
        csvMeasureTFHoverTime = ""
    }

    function updateMeasureHover(pointNorm) {
        if (!csvMeasurePending || !csvReplay.loaded || csvReplay.lineCount <= 0) return
        var row = Math.round(pointNorm.y * (replayWaterfallModel.height - 1))
        var frameIndex = csvReplay.currentIndex - row
        if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
        csvMeasureHoverFrameIndex = frameIndex
        csvMeasureHoverTime = csvReplay.timestampAt(frameIndex)
        csvMeasureHoverYNorm = pointNorm.y
    }

    function addOrFinishMeasure(pointNorm) {
        if (!csvReplay.loaded || csvReplay.lineCount <= 0) return
        var row = Math.round(pointNorm.y * (replayWaterfallModel.height - 1))
        var frameIndex = csvReplay.currentIndex - row
        if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
        if (!csvMeasurePending) {
            csvMeasurePending = true
            csvMeasureStartXNorm = pointNorm.x
            csvMeasureStartYNorm = pointNorm.y
            csvMeasureHoverYNorm = pointNorm.y
            csvMeasureStartFrameIndex = frameIndex
            csvMeasureStartTime = csvReplay.timestampAt(frameIndex)
            csvMeasureHoverFrameIndex = frameIndex
            csvMeasureHoverTime = csvMeasureStartTime
            return
        }

        var endFrame = frameIndex
        var startFrame = csvMeasureStartFrameIndex
        var startTime = csvMeasureStartTime
        var endTime = csvReplay.timestampAt(endFrame)
        var t0 = timestampToMs(startTime)
        var t1 = timestampToMs(endTime)
        var deltaMs = (!isNaN(t0) && !isNaN(t1)) ? Math.abs(t1 - t0) : 0

        pushCsvUndoSnapshot("add measure T")
        csvMeasureModel.append({
            xNorm: csvMeasureStartXNorm,
            anchorXNorm: csvMeasureStartXNorm,
            startFrameIndex: startFrame,
            endFrameIndex: endFrame,
            startTime: startTime,
            endTime: endTime,
            deltaMs: deltaMs,
            deltaText: formatDeltaTimeMs(deltaMs),
            color: "#ffd54f"
        })
        selectMeasureTAt(csvMeasureModel.count - 1)

        clearPendingMeasure()
    }

    function updateMeasureFHover(pointNorm) {
        if (!csvMeasureFPending || !csvReplay.loaded) return
        csvMeasureFHoverXNorm = pointNorm.x
    }

    function addOrFinishMeasureF(pointNorm) {
        if (!csvReplay.loaded || csvReplay.lineCount <= 0) return
        var row = Math.round(pointNorm.y * (replayWaterfallModel.height - 1))
        var frameIndex = csvReplay.currentIndex - row
        if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
        if (!csvMeasureFPending) {
            csvMeasureFPending = true
            csvMeasureFStartXNorm = pointNorm.x
            csvMeasureFStartYNorm = pointNorm.y
            csvMeasureFHoverXNorm = pointNorm.x
            csvMeasureFStartFrameIndex = frameIndex
            return
        }

        var x1 = csvMeasureFStartXNorm
        var x2 = pointNorm.x
        var f1 = csvFreqMin + x1 * (csvFreqMax - csvFreqMin)
        var f2 = csvFreqMin + x2 * (csvFreqMax - csvFreqMin)
        var delta = Math.abs(f2 - f1)

        pushCsvUndoSnapshot("add measure F")
        csvMeasureFModel.append({
            yNorm: 0.0,
            anchorYNorm: 0.0,
            x1Norm: x1,
            x2Norm: x2,
            frameIndex: csvMeasureFStartFrameIndex,
            anchorFrameIndex: csvMeasureFStartFrameIndex,
            deltaFreqMHz: delta,
            deltaText: formatDeltaFreqMHz(delta),
            color: "#4db6ff"
        })
        selectMeasureFAt(csvMeasureFModel.count - 1)

        csvMeasureFPending = false
        csvMeasureFStartXNorm = 0.5
        csvMeasureFStartYNorm = 0.5
        csvMeasureFHoverXNorm = 0.5
        csvMeasureFStartFrameIndex = -1
    }

    function updateMeasureTFHover(pointNorm) {
        if (!csvMeasureTFPending || !csvReplay.loaded || csvReplay.lineCount <= 0) return
        var row = Math.round(pointNorm.y * (replayWaterfallModel.height - 1))
        var frameIndex = csvReplay.currentIndex - row
        if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
        csvMeasureTFHoverXNorm = pointNorm.x
        csvMeasureTFHoverYNorm = pointNorm.y
        csvMeasureTFHoverFrameIndex = frameIndex
        csvMeasureTFHoverTime = csvReplay.timestampAt(frameIndex)
    }

    function addOrFinishMeasureTF(pointNorm) {
        if (!csvReplay.loaded || csvReplay.lineCount <= 0) return
        var row = Math.round(pointNorm.y * (replayWaterfallModel.height - 1))
        var frameIndex = csvReplay.currentIndex - row
        if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return

        if (!csvMeasureTFPending) {
            csvMeasureTFPending = true
            csvMeasureTFStartXNorm = pointNorm.x
            csvMeasureTFStartYNorm = pointNorm.y
            csvMeasureTFHoverXNorm = pointNorm.x
            csvMeasureTFHoverYNorm = pointNorm.y
            csvMeasureTFStartFrameIndex = frameIndex
            csvMeasureTFStartTime = csvReplay.timestampAt(frameIndex)
            csvMeasureTFHoverFrameIndex = frameIndex
            csvMeasureTFHoverTime = csvMeasureTFStartTime
            return
        }

        var startTime = csvMeasureTFStartTime
        var endTime = csvReplay.timestampAt(frameIndex)
        var t0 = timestampToMs(startTime)
        var t1 = timestampToMs(endTime)
        var deltaMs = (!isNaN(t0) && !isNaN(t1)) ? Math.abs(t1 - t0) : 0

        var f1 = csvFreqMin + csvMeasureTFStartXNorm * (csvFreqMax - csvFreqMin)
        var f2 = csvFreqMin + pointNorm.x * (csvFreqMax - csvFreqMin)
        var deltaF = Math.abs(f2 - f1)

        pushCsvUndoSnapshot("add measure TF")
        csvMeasureTFModel.append({
            x1Norm: csvMeasureTFStartXNorm,
            y1Norm: 0.0,
            x2Norm: pointNorm.x,
            y2Norm: 0.0,
            offsetXNorm: 0.0,
            offsetYNorm: 0.0,
            frame1Index: csvMeasureTFStartFrameIndex,
            frame2Index: frameIndex,
            deltaMs: deltaMs,
            deltaFreqMHz: deltaF,
            deltaTextT: formatDeltaTimeMs(deltaMs),
            deltaTextF: formatDeltaFreqMHz(deltaF),
            color: "#ffb74d"
        })
        selectMeasureTFAt(csvMeasureTFModel.count - 1)

        csvMeasureTFPending = false
        csvMeasureTFStartXNorm = 0.5
        csvMeasureTFStartYNorm = 0.5
        csvMeasureTFHoverXNorm = 0.5
        csvMeasureTFHoverYNorm = 0.5
        csvMeasureTFStartFrameIndex = -1
        csvMeasureTFStartTime = ""
        csvMeasureTFHoverFrameIndex = -1
        csvMeasureTFHoverTime = ""
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
                    Label { text: "Freq:" }
                    TextField {
                        id: liveFreqField
                        Layout.preferredWidth: 110
                        enabled: civClient.connected
                        inputMethodHints: Qt.ImhPreferNumbers
                        Component.onCompleted: text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
                        onAccepted: applyLiveFrequencyEdit()
                    }
                    ComboBox {
                        id: liveFreqUnitCombo
                        model: ["Hz", "kHz", "MHz"]
                        enabled: civClient.connected
                        currentIndex: 2
                        onCurrentTextChanged: {
                            liveFreqUnit = currentText
                            if (!liveFreqField.activeFocus) {
                                liveFreqField.text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
                            }
                        }
                    }
                    Connections {
                        target: civClient
                        function onFreqChanged() {
                            if (!liveFreqField.activeFocus) {
                                liveFreqField.text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
                            }
                        }
                        function onConnectedChanged() {
                            if (!liveFreqField.activeFocus) {
                                liveFreqField.text = formatLiveFrequencyForUnit(civClient.freqMHz, liveFreqUnit)
                            }
                            liveSpanKhz = civClient.spanKHz > 0 ? civClient.spanKHz : defaultSpanKhz
                            liveSpanCombo.currentIndex = spanOptionIndex(liveSpanKhz)
                            if (!liveRfGainSlider.pressed) {
                                liveRfGain = civClient.rfGain
                            }
                        }
                        function onSpanChanged() {
                            liveSpanKhz = civClient.spanKHz > 0 ? civClient.spanKHz : liveSpanKhz
                            liveSpanCombo.currentIndex = spanOptionIndex(liveSpanKhz)
                        }
                        function onRfGainChanged() {
                            if (!liveRfGainSlider.pressed) {
                                liveRfGain = civClient.rfGain
                            }
                        }
                    }
                    Button {
                        text: "Appliquer"
                        enabled: civClient.connected
                        onClicked: applyLiveFrequencyEdit()
                    }
                    Label { text: "Span:" }
                    ComboBox {
                        id: liveSpanCombo
                        enabled: civClient.connected
                        model: liveSpanOptionsKhz.map(function(v) { return Number(v).toString() + " kHz" })
                        currentIndex: spanOptionIndex(liveSpanKhz)
                        onActivated: applyLiveSpanSelection()
                    }
                    Label { text: "RF Gain:" }
                    Slider {
                        id: liveRfGainSlider
                        enabled: civClient.connected
                        from: 0
                        to: 255
                        stepSize: 1
                        snapMode: Slider.SnapAlways
                        Layout.preferredWidth: 150
                        value: liveRfGain
                        onMoved: applyLiveRfGain(value)
                        onPressedChanged: {
                            if (!pressed) {
                                applyLiveRfGain(value)
                            }
                        }
                    }
                    Label {
                        text: Math.round(liveRfGainSlider.value).toString()
                        Layout.preferredWidth: 30
                        horizontalAlignment: Text.AlignRight
                    }
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
                                Label { text: "dBm"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                Label { text: dbmMax.toFixed(0); anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                Label { text: dbmMid.toFixed(0); anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10; color: "white" }
                                Label { text: dbmMin.toFixed(0); anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10; color: "white" }
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                SpectrumItem {
                                    id: liveSpectrumDisplay
                                    anchors.fill: parent
                                    model: liveSpectrumModel
                                }

                                // Axis bars only (no label/layout changes)
                                Rectangle { x: 0; y: 0; width: 1; height: parent.height; color: "#8ea2ba"; opacity: 0.8 }
                                Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: "#8ea2ba"; opacity: 0.8 }
                                Repeater {
                                    model: 5
                                    delegate: Rectangle {
                                        width: 1
                                        height: 6
                                        color: "#8ea2ba"
                                        opacity: 0.9
                                        x: (index / 4) * (parent.width - 1)
                                        y: parent.height - height
                                    }
                                }
                                Repeater {
                                    model: 5
                                    delegate: Rectangle {
                                        width: 6
                                        height: 1
                                        color: "#8ea2ba"
                                        opacity: 0.9
                                        x: 0
                                        y: (index / 4) * (parent.height - 1)
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
                                Label { text: liveFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10; color: "white" }
                                Label { text: liveCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10; color: "white" }
                                Label { text: liveFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10; color: "white" }
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
                                Label { text: ""; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                Label { text: "--"; anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                Label { text: "--"; anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10; color: "white" }
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                WaterfallItem {
                                    id: liveWaterfallDisplay
                                    anchors.fill: parent
                                    model: liveWaterfallModel
                                    onHeightChanged: if (model) model.setHeight(Math.max(1, Math.round(height)))
                                    Component.onCompleted: if (model) model.setHeight(Math.max(1, Math.round(height)))
                                }

                                // Axis bars only (no label/layout changes)
                                Rectangle { x: 0; y: 0; width: 1; height: parent.height; color: "#8ea2ba"; opacity: 0.8 }
                                Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: "#8ea2ba"; opacity: 0.8 }
                                Repeater {
                                    model: 5
                                    delegate: Rectangle {
                                        width: 1
                                        height: 6
                                        color: "#8ea2ba"
                                        opacity: 0.9
                                        x: (index / 4) * (parent.width - 1)
                                        y: parent.height - height
                                    }
                                }
                                Repeater {
                                    model: 5
                                    delegate: Rectangle {
                                        width: 6
                                        height: 1
                                        color: "#8ea2ba"
                                        opacity: 0.9
                                        x: 0
                                        y: (index / 4) * (parent.height - 1)
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
                                Label { text: liveFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10; color: "white" }
                                Label { text: liveCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10; color: "white" }
                                Label { text: liveFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10; color: "white" }
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
                                        Label { text: "dBm"; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                        Label { text: csvDbmMax.toFixed(0); anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                        Label { text: csvDbmMid.toFixed(0); anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10; color: "white" }
                                        Label { text: csvDbmMin.toFixed(0); anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10; color: "white" }
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

                                        // Axis bars only (no label/layout changes)
                                        Rectangle { x: 0; y: 0; width: 1; height: parent.height; color: "#8ea2ba"; opacity: 0.8 }
                                        Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: "#8ea2ba"; opacity: 0.8 }
                                        Repeater {
                                            model: 5
                                            delegate: Rectangle {
                                                width: 1
                                                height: 6
                                                color: "#8ea2ba"
                                                opacity: 0.9
                                                x: (index / 4) * (parent.width - 1)
                                                y: parent.height - height
                                            }
                                        }
                                        Repeater {
                                            model: 5
                                            delegate: Rectangle {
                                                width: 6
                                                height: 1
                                                color: "#8ea2ba"
                                                opacity: 0.9
                                                x: 0
                                                y: (index / 4) * (parent.height - 1)
                                            }
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
                                        Label { text: csvFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10; color: "white" }
                                        Label { text: csvCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10; color: "white" }
                                        Label { text: csvFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10; color: "white" }
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
                                        Label { text: ""; anchors.left: parent.left; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                        Label { text: csvWfTopTime; anchors.right: parent.right; anchors.top: parent.top; font.pixelSize: 10; color: "white" }
                                        Label { text: csvWfBottomTime; anchors.right: parent.right; anchors.bottom: parent.bottom; font.pixelSize: 10; color: "white" }
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

                                        // Axis bars only (no label/layout changes)
                                        Rectangle { x: 0; y: 0; width: 1; height: parent.height; color: "#8ea2ba"; opacity: 0.8 }
                                        Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: "#8ea2ba"; opacity: 0.8 }
                                        Repeater {
                                            model: 5
                                            delegate: Rectangle {
                                                width: 1
                                                height: 6
                                                color: "#8ea2ba"
                                                opacity: 0.9
                                                x: (index / 4) * (parent.width - 1)
                                                y: parent.height - height
                                            }
                                        }
                                        Repeater {
                                            model: 5
                                            delegate: Rectangle {
                                                width: 6
                                                height: 1
                                                color: "#8ea2ba"
                                                opacity: 0.9
                                                x: 0
                                                y: (index / 4) * (parent.height - 1)
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
                                            cursorShape: (csvZoomMode || csvMeasureMode || csvMeasureFMode || csvMeasureTFMode) ? Qt.CrossCursor : Qt.ArrowCursor
                                            property bool zoomSelecting: false
                                            property real selStartX: 0
                                            property real selStartY: 0
                                            property real selEndX: 0
                                            property real selEndY: 0

                                            onPressed: function(mouse) {
                                                if (csvMeasureMode) {
                                                    var nPress = screenToNorm(mouse.x, mouse.y)
                                                    addOrFinishMeasure(nPress)
                                                    return
                                                }
                                                if (csvMeasureFMode) {
                                                    var nPressF = screenToNorm(mouse.x, mouse.y)
                                                    addOrFinishMeasureF(nPressF)
                                                    return
                                                }
                                                if (csvMeasureTFMode) {
                                                    var nPressTF = screenToNorm(mouse.x, mouse.y)
                                                    addOrFinishMeasureTF(nPressTF)
                                                    return
                                                }
                                                if (!csvZoomMode) return
                                                zoomSelecting = true
                                                selStartX = mouse.x
                                                selStartY = mouse.y
                                                selEndX = mouse.x
                                                selEndY = mouse.y
                                            }
                                            onPositionChanged: function(mouse) {
                                                if (zoomSelecting) {
                                                    selEndX = mouse.x
                                                    selEndY = mouse.y
                                                }
                                                if (csvMeasureMode && csvMeasurePending) {
                                                    var n = screenToNorm(mouse.x, mouse.y)
                                                    updateMeasureHover(n)
                                                }
                                                if (csvMeasureFMode && csvMeasureFPending) {
                                                    var nf = screenToNorm(mouse.x, mouse.y)
                                                    updateMeasureFHover(nf)
                                                }
                                                if (csvMeasureTFMode && csvMeasureTFPending) {
                                                    var ntf = screenToNorm(mouse.x, mouse.y)
                                                    updateMeasureTFHover(ntf)
                                                }
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
                                                if (csvZoomMode) return
                                                if (csvMeasureMode || csvMeasureFMode || csvMeasureTFMode) return
                                                if (csvToolMode !== "marker") return
                                                var n = screenToNorm(mouse.x, mouse.y)
                                                if (!csvReplay.loaded) return
                                                var row = Math.round(n.y * (replayWaterfallModel.height - 1))
                                                var frameIndex = csvReplay.currentIndex - row
                                                if (frameIndex < 0 || frameIndex >= csvReplay.lineCount) return
                                                var xIdx = Math.round(n.x * (replayWaterfallModel.width - 1))
                                                var freq = csvFreqMin + n.x * (csvFreqMax - csvFreqMin)
                                                var dbm = replayWaterfallModel.valueAt(xIdx, row)
                                                var timeText = csvReplay.timestampAt(frameIndex)
                                                pushCsvUndoSnapshot("add marker")
                                                csvMarkersModel.append({ xNorm: n.x, frameIndex: frameIndex, color: csvNextMarkerColor, freq: freq, dbm: dbm, time: timeText })
                                                selectMarkerAt(csvMarkersModel.count - 1)
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
                                                property bool selected: csvMarkerSelectedIndex === index
                                                Rectangle { x: px - 6; y: py - 1.5; width: 12; height: 3; color: markerColor; opacity: selected ? 1.0 : 0.9 }
                                                Rectangle { x: px - 1.5; y: py - 6; width: 3; height: 12; color: markerColor; opacity: selected ? 1.0 : 0.9 }
                                                Rectangle {
                                                    id: markerLabelBg
                                                    width: markerLabel.implicitWidth + 8
                                                    height: markerLabel.implicitHeight + 4
                                                    x: px + (px > parent.width * 0.6 ? -width - 6 : 6)
                                                    y: py + (py > parent.height * 0.6 ? -height - 6 : 6)
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: selected ? "#ffffff" : markerColor
                                                    border.width: selected ? 2 : 1
                                                    radius: 3
                                                    Text { id: markerLabel; anchors.centerIn: parent; text: freq.toFixed(6) + " MHz\n" + dbm.toFixed(1) + " dBm\n" + timeText; color: "white"; font.pixelSize: 9 }
                                                }
                                                MouseArea {
                                                    x: px - 9
                                                    y: py - 9
                                                    width: 18
                                                    height: 18
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("delete marker")
                                                            csvMarkersModel.remove(index)
                                                            clearSelectionCsv()
                                                        } else {
                                                            selectMarkerAt(index)
                                                        }
                                                    }
                                                }
                                                MouseArea {
                                                    anchors.fill: markerLabelBg
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("delete marker")
                                                            csvMarkersModel.remove(index)
                                                            clearSelectionCsv()
                                                        } else {
                                                            selectMarkerAt(index)
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        Item {
                                            id: measurePreview
                                            anchors.fill: parent
                                            visible: csvMeasurePending && csvMeasureStartFrameIndex >= 0 &&
                                                     csvMeasureHoverFrameIndex >= 0 && replayWaterfallModel.height > 0
                                            property real px: mapZoomX(csvMeasureStartXNorm)
                                            property real pyA: mapZoomY(csvMeasureStartYNorm)
                                            property real pyB: mapZoomY(csvMeasureHoverYNorm)
                                            property real yTop: Math.min(pyA, pyB)
                                            property real yBottom: Math.max(pyA, pyB)
                                            property real midY: (yTop + yBottom) * 0.5
                                            property bool inView: px >= 0 && px <= width &&
                                                                  yBottom >= 0 && yTop <= height

                                            Rectangle { visible: measurePreview.inView; x: measurePreview.px - 1; y: measurePreview.yTop; width: 2; height: Math.max(2, measurePreview.yBottom - measurePreview.yTop); color: "#ffd54f" }
                                            Rectangle { visible: measurePreview.inView; x: measurePreview.px - 8; y: measurePreview.yTop - 1; width: 16; height: 2; color: "#ffd54f" }
                                            Rectangle { visible: measurePreview.inView; x: measurePreview.px - 8; y: measurePreview.yBottom - 1; width: 16; height: 2; color: "#ffd54f" }

                                            Rectangle {
                                                visible: measurePreview.inView
                                                x: measurePreview.px + 10
                                                y: measurePreview.midY - (pendingMeasureLabel.implicitHeight + 4) * 0.5
                                                width: pendingMeasureLabel.implicitWidth + 8
                                                height: pendingMeasureLabel.implicitHeight + 4
                                                radius: 3
                                                color: "#000000"
                                                opacity: 0.75
                                                border.color: "#ffd54f"
                                                Text {
                                                    id: pendingMeasureLabel
                                                    anchors.centerIn: parent
                                                    text: "\u0394T: " + deltaTextFromTimes(csvMeasureStartTime, csvMeasureHoverTime)
                                                    color: "white"
                                                    font.pixelSize: 9
                                                }
                                            }
                                        }

                                        Item {
                                            id: measureFPreview
                                            anchors.fill: parent
                                            visible: csvMeasureFPending && replayWaterfallModel.height > 0
                                            property real py: mapZoomY(csvMeasureFStartYNorm)
                                            property real xA: mapZoomX(csvMeasureFStartXNorm)
                                            property real xB: mapZoomX(csvMeasureFHoverXNorm)
                                            property real xLeft: Math.min(xA, xB)
                                            property real xRight: Math.max(xA, xB)
                                            property real midX: (xLeft + xRight) * 0.5
                                            property bool inView: py >= 0 && py <= height && xRight >= 0 && xLeft <= width
                                            property real fA: csvFreqMin + csvMeasureFStartXNorm * (csvFreqMax - csvFreqMin)
                                            property real fB: csvFreqMin + csvMeasureFHoverXNorm * (csvFreqMax - csvFreqMin)

                                            Rectangle { visible: measureFPreview.inView; x: measureFPreview.xLeft; y: measureFPreview.py - 1; width: Math.max(2, measureFPreview.xRight - measureFPreview.xLeft); height: 2; color: "#4db6ff" }
                                            Rectangle { visible: measureFPreview.inView; x: measureFPreview.xLeft - 1; y: measureFPreview.py - 8; width: 2; height: 16; color: "#4db6ff" }
                                            Rectangle { visible: measureFPreview.inView; x: measureFPreview.xRight - 1; y: measureFPreview.py - 8; width: 2; height: 16; color: "#4db6ff" }

                                            Rectangle {
                                                visible: measureFPreview.inView
                                                x: Math.max(0, Math.min(parent.width - width, measureFPreview.midX - width * 0.5))
                                                y: Math.max(0, Math.min(parent.height - height, measureFPreview.py + 10))
                                                width: pendingMeasureFLabel.implicitWidth + 8
                                                height: pendingMeasureFLabel.implicitHeight + 4
                                                radius: 3
                                                color: "#000000"
                                                opacity: 0.75
                                                border.color: "#4db6ff"
                                                Text {
                                                    id: pendingMeasureFLabel
                                                    anchors.centerIn: parent
                                                    text: "\u0394F: " + formatDeltaFreqMHz(Math.abs(measureFPreview.fB - measureFPreview.fA))
                                                    color: "white"
                                                    font.pixelSize: 9
                                                }
                                            }
                                        }

                                        Item {
                                            id: measureTFPreview
                                            anchors.fill: parent
                                            visible: csvMeasureTFPending && csvMeasureTFStartFrameIndex >= 0 &&
                                                     csvMeasureTFHoverFrameIndex >= 0 && replayWaterfallModel.height > 0
                                            property real x1: mapZoomX(csvMeasureTFStartXNorm)
                                            property real y1: mapZoomY(csvMeasureTFStartYNorm)
                                            property real x2: mapZoomX(csvMeasureTFHoverXNorm)
                                            property real y2: mapZoomY(csvMeasureTFHoverYNorm)
                                            property real dx: x2 - x1
                                            property real dy: y2 - y1
                                            property real segLen: Math.max(1, Math.sqrt(dx * dx + dy * dy))
                                            property real angleDeg: Math.atan2(dy, dx) * 180.0 / Math.PI
                                            property real nx: -dy / segLen
                                            property real ny: dx / segLen
                                            property real cap: 8
                                            property real fA: csvFreqMin + csvMeasureTFStartXNorm * (csvFreqMax - csvFreqMin)
                                            property real fB: csvFreqMin + csvMeasureTFHoverXNorm * (csvFreqMax - csvFreqMin)
                                            property real midX: (x1 + x2) * 0.5
                                            property real midY: (y1 + y2) * 0.5

                                            Rectangle {
                                                x: measureTFPreview.x1
                                                y: measureTFPreview.y1 - 1
                                                width: measureTFPreview.segLen
                                                height: 2
                                                color: "#ffb74d"
                                                transformOrigin: Item.Left
                                                rotation: measureTFPreview.angleDeg
                                            }
                                            Rectangle {
                                                x: measureTFPreview.x1 - measureTFPreview.cap
                                                y: measureTFPreview.y1 - 1
                                                width: measureTFPreview.cap * 2
                                                height: 2
                                                color: "#ffb74d"
                                                transformOrigin: Item.Center
                                                rotation: measureTFPreview.angleDeg + 90
                                            }
                                            Rectangle {
                                                x: measureTFPreview.x2 - measureTFPreview.cap
                                                y: measureTFPreview.y2 - 1
                                                width: measureTFPreview.cap * 2
                                                height: 2
                                                color: "#ffb74d"
                                                transformOrigin: Item.Center
                                                rotation: measureTFPreview.angleDeg + 90
                                            }

                                            Rectangle {
                                                width: pendingMeasureTFLabel.implicitWidth + 8
                                                height: pendingMeasureTFLabel.implicitHeight + 4
                                                x: Math.max(0, Math.min(parent.width - width, measureTFPreview.midX + measureTFPreview.nx * 14))
                                                y: Math.max(0, Math.min(parent.height - height, measureTFPreview.midY + measureTFPreview.ny * 14))
                                                radius: 3
                                                color: "#000000"
                                                opacity: 0.75
                                                border.color: "#ffb74d"
                                                Text {
                                                    id: pendingMeasureTFLabel
                                                    anchors.centerIn: parent
                                                    text: "\u0394T: " + deltaTextFromTimes(csvMeasureTFStartTime, csvMeasureTFHoverTime) +
                                                          "\n\u0394F: " + formatDeltaFreqMHz(Math.abs(measureTFPreview.fB - measureTFPreview.fA))
                                                    color: "white"
                                                    font.pixelSize: 9
                                                }
                                            }
                                        }

                                        Repeater {
                                            model: csvMeasureModel
                                            delegate: Item {
                                                anchors.fill: parent
                                                property int rowA: csvReplay.currentIndex - model.startFrameIndex
                                                property int rowB: csvReplay.currentIndex - model.endFrameIndex
                                                property int rowMin: Math.min(rowA, rowB)
                                                property int rowMax: Math.max(rowA, rowB)
                                                property bool inView: replayWaterfallModel.height > 0 && rowMax >= 0 && rowMin <= (replayWaterfallModel.height - 1)
                                                visible: inView

                                                property real anchorXNorm: model.anchorXNorm !== undefined ? model.anchorXNorm : model.xNorm
                                                property real xNorm: model.xNorm
                                                property real pxAnchor: mapZoomX(anchorXNorm)
                                                property real pxDim: mapZoomX(xNorm)
                                                property real hDen: Math.max(1, replayWaterfallModel.height - 1)
                                                property real pyA: mapZoomY(rowA / hDen)
                                                property real pyB: mapZoomY(rowB / hDen)
                                                property real yTop: Math.min(pyA, pyB)
                                                property real yBottom: Math.max(pyA, pyB)
                                                property real midY: (yTop + yBottom) * 0.5
                                                property bool selected: csvMeasureSelectedIndex === index
                                                property string measureColor: selected ? "#ffeb3b" : (model.color ? model.color : "#ffd54f")
                                                property real offsetX: pxDim - pxAnchor
                                                property real capShort: 8
                                                property real capLong: Math.max(capShort, Math.min(34, Math.abs(offsetX) + 6))
                                                property real capLeft: offsetX >= 0 ? capLong : capShort
                                                property real capRight: offsetX >= 0 ? capShort : capLong

                                                // Lignes d'attache (type CAO): longueur variable selon l'offset
                                                Rectangle {
                                                    x: Math.min(pxAnchor, pxDim)
                                                    y: yTop - 1
                                                    width: Math.max(1, Math.abs(pxDim - pxAnchor))
                                                    height: 2
                                                    color: measureColor
                                                }
                                                Rectangle {
                                                    x: Math.min(pxAnchor, pxDim)
                                                    y: yBottom - 1
                                                    width: Math.max(1, Math.abs(pxDim - pxAnchor))
                                                    height: 2
                                                    color: measureColor
                                                }

                                                // Ligne de cote
                                                Rectangle { x: pxDim - 1; y: yTop; width: 2; height: Math.max(2, yBottom - yTop); color: measureColor }
                                                // Embouts perpendiculaires
                                                Rectangle { x: pxDim - capLeft; y: yTop - 1; width: capLeft + capRight; height: 2; color: measureColor }
                                                Rectangle { x: pxDim - capLeft; y: yBottom - 1; width: capLeft + capRight; height: 2; color: measureColor }

                                                Rectangle {
                                                    id: measureLabelBg
                                                    property real marginX: 10
                                                    property real desiredX: offsetX >= 0
                                                                            ? (pxDim + marginX) // cote court a droite si decale a droite
                                                                            : (pxDim - width - marginX) // cote court a gauche si decale a gauche
                                                    x: Math.max(0, Math.min(parent.width - width, desiredX))
                                                    y: midY - (measureLabel.implicitHeight + 4) * 0.5
                                                    width: measureLabel.implicitWidth + 8
                                                    height: measureLabel.implicitHeight + 4
                                                    radius: 3
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: measureColor
                                                    Text {
                                                        id: measureLabel
                                                        anchors.centerIn: parent
                                                        text: "\u0394T: " + (model.deltaText ? model.deltaText : "--")
                                                        color: "white"
                                                        font.pixelSize: 9
                                                    }
                                                }

                                                MouseArea {
                                                    x: Math.min(pxAnchor, pxDim) - 14
                                                    y: yTop - 10
                                                    width: Math.max(30, measureLabelBg.x + measureLabelBg.width - x + 10)
                                                    height: Math.max(20, yBottom - yTop + 20)
                                                    enabled: csvToolMode === "mouse"
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    hoverEnabled: true
                                                    preventStealing: true
                                                    cursorShape: Qt.SizeHorCursor
                                                    property bool dragging: false
                                                    property real dragDx: 0
                                                    function mouseXInDelegate(mouse) {
                                                        return mapToItem(parent, mouse.x, mouse.y).x
                                                    }
                                                    onPressed: function(mouse) {
                                                        if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureTAt(index)
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("move measure T")
                                                            dragging = true
                                                            dragDx = pxDim - mouseXInDelegate(mouse)
                                                        }
                                                    }
                                                    onPositionChanged: function(mouse) {
                                                        if (csvToolMode !== "mouse") return
                                                        if (!dragging) return
                                                        var targetX = mouseXInDelegate(mouse) + dragDx
                                                        var nx = screenToNorm(targetX, midY).x
                                                        csvMeasureModel.setProperty(index, "xNorm", nx)
                                                    }
                                                    onReleased: dragging = false
                                                    onCanceled: dragging = false
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("delete measure T")
                                                            csvMeasureModel.remove(index)
                                                            clearSelectionCsv()
                                                        } else if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureTAt(index)
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        Repeater {
                                            model: csvMeasureFModel
                                            delegate: Item {
                                                anchors.fill: parent
                                                property real yNormOffset: model.yNorm
                                                property real anchorYNormOffset: model.anchorYNorm !== undefined ? model.anchorYNorm : model.yNorm
                                                property int frameIndex: model.frameIndex !== undefined ? model.frameIndex : -1
                                                property int anchorFrameIndex: model.anchorFrameIndex !== undefined ? model.anchorFrameIndex : frameIndex
                                                property real x1Norm: model.x1Norm
                                                property real x2Norm: model.x2Norm
                                                property real hDen: Math.max(1, replayWaterfallModel.height - 1)
                                                property int rowDim: frameIndex >= 0 ? (csvReplay.currentIndex - frameIndex) : -1
                                                property int rowAnchor: anchorFrameIndex >= 0 ? (csvReplay.currentIndex - anchorFrameIndex) : -1
                                                property real yBaseNorm: frameIndex >= 0 ? (rowDim / hDen) : 0
                                                property real yAnchorBaseNorm: anchorFrameIndex >= 0 ? (rowAnchor / hDen) : 0
                                                property real pyAnchor: mapZoomY(yAnchorBaseNorm + anchorYNormOffset)
                                                property real pyDim: mapZoomY(yBaseNorm + yNormOffset)
                                                property real x1: mapZoomX(x1Norm)
                                                property real x2: mapZoomX(x2Norm)
                                                property real xLeft: Math.min(x1, x2)
                                                property real xRight: Math.max(x1, x2)
                                                property real midX: (xLeft + xRight) * 0.5
                                                property bool inView: xRight >= 0 && xLeft <= width &&
                                                                      Math.max(pyAnchor, pyDim) >= 0 &&
                                                                      Math.min(pyAnchor, pyDim) <= height
                                                property bool selected: csvMeasureFSelectedIndex === index
                                                property string measureColor: selected ? "#81d4fa" : (model.color ? model.color : "#4db6ff")
                                                property real offsetY: pyDim - pyAnchor
                                                property real capShort: 8
                                                property real capLong: Math.max(capShort, Math.min(34, Math.abs(offsetY) + 6))
                                                property real capTop: offsetY >= 0 ? capLong : capShort
                                                property real capBottom: offsetY >= 0 ? capShort : capLong

                                                Rectangle { x: x1 - 1; y: Math.min(pyAnchor, pyDim); width: 2; height: Math.max(1, Math.abs(pyDim - pyAnchor)); color: measureColor }
                                                Rectangle { x: x2 - 1; y: Math.min(pyAnchor, pyDim); width: 2; height: Math.max(1, Math.abs(pyDim - pyAnchor)); color: measureColor }

                                                Rectangle { x: xLeft; y: pyDim - 1; width: Math.max(2, xRight - xLeft); height: 2; color: measureColor }
                                                Rectangle { x: xLeft - 1; y: pyDim - capTop; width: 2; height: capTop + capBottom; color: measureColor }
                                                Rectangle { x: xRight - 1; y: pyDim - capTop; width: 2; height: capTop + capBottom; color: measureColor }

                                                Rectangle {
                                                    id: measureFLabelBg
                                                    property real marginY: 10
                                                    property real desiredY: offsetY >= 0
                                                                            ? (pyDim + marginY)
                                                                            : (pyDim - height - marginY)
                                                    x: Math.max(0, Math.min(parent.width - width, midX - width * 0.5))
                                                    y: Math.max(0, Math.min(parent.height - height, desiredY))
                                                    width: measureFLabel.implicitWidth + 8
                                                    height: measureFLabel.implicitHeight + 4
                                                    radius: 3
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: measureColor
                                                    Text {
                                                        id: measureFLabel
                                                        anchors.centerIn: parent
                                                        text: "\u0394F: " + (model.deltaText ? model.deltaText : "--")
                                                        color: "white"
                                                        font.pixelSize: 9
                                                    }
                                                }

                                                MouseArea {
                                                    x: xLeft - 10
                                                    y: Math.min(pyAnchor, pyDim) - 14
                                                    width: Math.max(24, xRight - xLeft + 20)
                                                    height: Math.max(28, Math.abs(pyDim - pyAnchor) + 28)
                                                    enabled: csvToolMode === "mouse"
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    hoverEnabled: true
                                                    preventStealing: true
                                                    cursorShape: Qt.SizeVerCursor
                                                    property bool dragging: false
                                                    property real dragDy: 0
                                                    function mouseYInDelegate(mouse) {
                                                        return mapToItem(parent, mouse.x, mouse.y).y
                                                    }
                                                    onPressed: function(mouse) {
                                                        if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureFAt(index)
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("move measure F")
                                                            dragging = true
                                                            dragDy = pyDim - mouseYInDelegate(mouse)
                                                        }
                                                    }
                                                    onPositionChanged: function(mouse) {
                                                        if (csvToolMode !== "mouse") return
                                                        if (!dragging) return
                                                        var targetY = mouseYInDelegate(mouse) + dragDy
                                                        var ny = screenToNorm(midX, targetY).y
                                                        var yBase = frameIndex >= 0 ? (rowDim / hDen) : 0
                                                        csvMeasureFModel.setProperty(index, "yNorm", ny - yBase)
                                                    }
                                                    onReleased: dragging = false
                                                    onCanceled: dragging = false
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("delete measure F")
                                                            csvMeasureFModel.remove(index)
                                                            clearSelectionCsv()
                                                        } else if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureFAt(index)
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        Repeater {
                                            model: csvMeasureTFModel
                                            delegate: Item {
                                                anchors.fill: parent
                                                property real x1Norm: model.x1Norm
                                                property real y1Norm: model.y1Norm
                                                property real x2Norm: model.x2Norm
                                                property real y2Norm: model.y2Norm
                                                property int frame1Index: model.frame1Index !== undefined ? model.frame1Index : -1
                                                property int frame2Index: model.frame2Index !== undefined ? model.frame2Index : -1
                                                property real hDen: Math.max(1, replayWaterfallModel.height - 1)
                                                property int row1: frame1Index >= 0 ? (csvReplay.currentIndex - frame1Index) : -1
                                                property int row2: frame2Index >= 0 ? (csvReplay.currentIndex - frame2Index) : -1
                                                property real y1BaseNorm: frame1Index >= 0 ? (row1 / hDen) : y1Norm
                                                property real y2BaseNorm: frame2Index >= 0 ? (row2 / hDen) : y2Norm
                                                property real offsetXNorm: model.offsetXNorm !== undefined ? model.offsetXNorm : 0.0
                                                property real offsetYNorm: model.offsetYNorm !== undefined ? model.offsetYNorm : 0.0
                                                property real ax1: mapZoomX(x1Norm)
                                                property real ay1: mapZoomY(y1BaseNorm)
                                                property real ax2: mapZoomX(x2Norm)
                                                property real ay2: mapZoomY(y2BaseNorm)
                                                property real x1: mapZoomX(x1Norm + offsetXNorm)
                                                property real y1: mapZoomY(y1BaseNorm + offsetYNorm)
                                                property real x2: mapZoomX(x2Norm + offsetXNorm)
                                                property real y2: mapZoomY(y2BaseNorm + offsetYNorm)
                                                property real dx: x2 - x1
                                                property real dy: y2 - y1
                                                property real segLen: Math.max(1, Math.sqrt(dx * dx + dy * dy))
                                                property real angleDeg: Math.atan2(dy, dx) * 180.0 / Math.PI
                                                property real nx: -dy / segLen
                                                property real ny: dx / segLen
                                                property bool selected: csvMeasureTFSelectedIndex === index
                                                property string measureColor: selected ? "#ffd180" : (model.color ? model.color : "#ffb74d")
                                                property real ext1dx: x1 - ax1
                                                property real ext1dy: y1 - ay1
                                                property real ext1Len: Math.max(0.001, Math.sqrt(ext1dx * ext1dx + ext1dy * ext1dy))
                                                property real ext1Ang: Math.atan2(ext1dy, ext1dx) * 180.0 / Math.PI
                                                property real ext2dx: x2 - ax2
                                                property real ext2dy: y2 - ay2
                                                property real ext2Len: Math.max(0.001, Math.sqrt(ext2dx * ext2dx + ext2dy * ext2dy))
                                                property real ext2Ang: Math.atan2(ext2dy, ext2dx) * 180.0 / Math.PI
                                                property real cap: 8
                                                property real offsetMag: Math.sqrt(ext1dx * ext1dx + ext1dy * ext1dy)
                                                property real labelDist: 16
                                                property real offsetScalarPx: ext1dx * nx + ext1dy * ny
                                                property real labelSign: offsetScalarPx >= 0 ? 1 : -1
                                                property real midX: (x1 + x2) * 0.5
                                                property real midY: (y1 + y2) * 0.5
                                                property real minX: Math.min(Math.min(ax1, ax2), Math.min(x1, x2))
                                                property real maxX: Math.max(Math.max(ax1, ax2), Math.max(x1, x2))
                                                property real minY: Math.min(Math.min(ay1, ay2), Math.min(y1, y2))
                                                property real maxY: Math.max(Math.max(ay1, ay2), Math.max(y1, y2))

                                                Rectangle {
                                                    visible: ext1Len > 0.5
                                                    x: ax1
                                                    y: ay1 - 1
                                                    width: ext1Len
                                                    height: 2
                                                    color: measureColor
                                                    transformOrigin: Item.Left
                                                    rotation: ext1Ang
                                                }
                                                Rectangle {
                                                    visible: ext2Len > 0.5
                                                    x: ax2
                                                    y: ay2 - 1
                                                    width: ext2Len
                                                    height: 2
                                                    color: measureColor
                                                    transformOrigin: Item.Left
                                                    rotation: ext2Ang
                                                }

                                                Rectangle {
                                                    x: x1
                                                    y: y1 - 1
                                                    width: segLen
                                                    height: 2
                                                    color: measureColor
                                                    transformOrigin: Item.Left
                                                    rotation: angleDeg
                                                }
                                                Rectangle {
                                                    x: x1 - cap
                                                    y: y1 - 1
                                                    width: cap * 2
                                                    height: 2
                                                    color: measureColor
                                                    transformOrigin: Item.Center
                                                    rotation: angleDeg + 90
                                                }
                                                Rectangle {
                                                    x: x2 - cap
                                                    y: y2 - 1
                                                    width: cap * 2
                                                    height: 2
                                                    color: measureColor
                                                    transformOrigin: Item.Center
                                                    rotation: angleDeg + 90
                                                }

                                                Rectangle {
                                                    id: measureTFLabelBg
                                                    width: measureTFLabel.implicitWidth + 8
                                                    height: measureTFLabel.implicitHeight + 4
                                                    x: Math.max(0, Math.min(parent.width - width, midX + nx * labelDist * labelSign))
                                                    y: Math.max(0, Math.min(parent.height - height, midY + ny * labelDist * labelSign))
                                                    radius: 3
                                                    color: "#000000"
                                                    opacity: 0.75
                                                    border.color: measureColor
                                                    Text {
                                                        id: measureTFLabel
                                                        anchors.centerIn: parent
                                                        text: "\u0394T: " + (model.deltaTextT ? model.deltaTextT : "--") +
                                                              "\n\u0394F: " + (model.deltaTextF ? model.deltaTextF : "--")
                                                        color: "white"
                                                        font.pixelSize: 9
                                                    }
                                                }

                                                MouseArea {
                                                    x: minX - 14
                                                    y: minY - 14
                                                    width: Math.max(28, maxX - minX + 28)
                                                    height: Math.max(28, maxY - minY + 28)
                                                    enabled: csvToolMode === "mouse"
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    hoverEnabled: true
                                                    preventStealing: true
                                                    cursorShape: Qt.SizeAllCursor
                                                    property bool dragging: false
                                                    property real dragStartProjPx: 0
                                                    property real dragStartMidX: 0
                                                    property real dragStartMidY: 0
                                                    property real dragStartOffsetX: 0
                                                    property real dragStartOffsetY: 0

                                                    function mouseInOverlay(mouse) {
                                                        return mapToItem(parent, mouse.x, mouse.y)
                                                    }
                                                    function pointerProjPx(mouse) {
                                                        var p = mouseInOverlay(mouse)
                                                        return p.x * nx + p.y * ny
                                                    }

                                                    onPressed: function(mouse) {
                                                        if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureTFAt(index)
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("move measure TF")
                                                            dragStartProjPx = pointerProjPx(mouse)
                                                            dragStartMidX = midX
                                                            dragStartMidY = midY
                                                            dragStartOffsetX = offsetXNorm
                                                            dragStartOffsetY = offsetYNorm
                                                            dragging = true
                                                        }
                                                    }
                                                    onPositionChanged: function(mouse) {
                                                        if (csvToolMode !== "mouse") return
                                                        if (!dragging) return
                                                        var proj = pointerProjPx(mouse)
                                                        var deltaPx = proj - dragStartProjPx
                                                        var targetMidX = dragStartMidX + nx * deltaPx
                                                        var targetMidY = dragStartMidY + ny * deltaPx
                                                        var n0 = screenToNorm(dragStartMidX, dragStartMidY)
                                                        var n1 = screenToNorm(targetMidX, targetMidY)
                                                        csvMeasureTFModel.setProperty(index, "offsetXNorm", dragStartOffsetX + (n1.x - n0.x))
                                                        csvMeasureTFModel.setProperty(index, "offsetYNorm", dragStartOffsetY + (n1.y - n0.y))
                                                    }
                                                    onReleased: dragging = false
                                                    onCanceled: dragging = false
                                                    onClicked: function(mouse) {
                                                        if (mouse.button === Qt.RightButton) {
                                                            if (csvToolMode !== "mouse") return
                                                            pushCsvUndoSnapshot("delete measure TF")
                                                            csvMeasureTFModel.remove(index)
                                                            clearSelectionCsv()
                                                        } else if (mouse.button === Qt.LeftButton) {
                                                            selectMeasureTFAt(index)
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
                                        Label { text: csvFreqMin.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft; font.pixelSize: 10; color: "white" }
                                        Label { text: csvCenterFreq.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10; color: "white" }
                                        Label { text: csvFreqMax.toFixed(6); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 10; color: "white" }
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
                                    title: "Outils"
                                    Layout.fillWidth: true

                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 8

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Button {
                                                id: mouseToolButton
                                                text: "\uD83D\uDDB1"
                                                checkable: true
                                                checked: csvToolMode === "mouse"
                                                implicitWidth: markerToolButton.implicitWidth
                                                implicitHeight: markerToolButton.implicitHeight
                                                onClicked: setCsvTool("mouse")
                                            }
                                            Item { Layout.fillWidth: true }
                                        }

                                        Label {
                                            text: "Curseurs spectre"
                                            font.pixelSize: 10
                                            color: "#cfd8dc"
                                        }

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

                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 1
                                            color: "#2a2a2a"
                                        }

                                        Label {
                                            text: "Markers waterfall"
                                            font.pixelSize: 10
                                            color: "#cfd8dc"
                                        }

                                        Button {
                                            id: markerToolButton
                                            text: "\uD83D\uDCCD"
                                            checkable: true
                                            checked: csvToolMode === "marker"
                                            enabled: csvReplay.loaded
                                            onClicked: setCsvTool("marker")
                                        }

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

                                        Button {
                                            text: "Clear markers"
                                            onClicked: {
                                                if (csvMarkersModel.count <= 0) return
                                                pushCsvUndoSnapshot("clear markers")
                                                csvMarkersModel.clear()
                                                root.csvMarkerSelectedIndex = -1
                                            }
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 1
                                            color: "#2a2a2a"
                                        }

                                        Label {
                                            text: "Mesures"
                                            font.pixelSize: 10
                                            color: "#cfd8dc"
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Button {
                                                text: "\u0394T"
                                                checkable: true
                                                checked: csvToolMode === "measureT"
                                                enabled: csvReplay.loaded
                                                onClicked: setCsvTool("measureT")
                                            }
                                            Button {
                                                text: "\u0394F"
                                                checkable: true
                                                checked: csvToolMode === "measureF"
                                                enabled: csvReplay.loaded
                                                onClicked: setCsvTool("measureF")
                                            }
                                            Button {
                                                text: "\u0394T/\u0394F"
                                                checkable: true
                                                checked: csvToolMode === "measureTF"
                                                enabled: csvReplay.loaded
                                                onClicked: setCsvTool("measureTF")
                                            }
                                        }

                                        Label {
                                            text: csvMeasurePending ? "\u0394T attente 2eme clic..." :
                                                  (csvMeasureFPending ? "\u0394F attente 2eme clic..." :
                                                  (csvMeasureTFPending ? "\u0394T/\u0394F attente 2eme clic..." :
                                                  ((csvMeasureModel.count + csvMeasureFModel.count + csvMeasureTFModel.count) + " mesure(s)")))
                                            font.pixelSize: 10
                                            color: (csvMeasurePending || csvMeasureFPending || csvMeasureTFPending) ? "#ffd54f" : "#cfd8dc"
                                        }

                                        Button {
                                            text: "Clear mesures"
                                            onClicked: {
                                                if (csvMeasureModel.count + csvMeasureFModel.count + csvMeasureTFModel.count <= 0) return
                                                pushCsvUndoSnapshot("clear mesures")
                                                csvMeasureModel.clear()
                                                csvMeasureFModel.clear()
                                                csvMeasureTFModel.clear()
                                                root.csvMeasureSelectedIndex = -1
                                                root.csvMeasureFSelectedIndex = -1
                                                root.csvMeasureTFSelectedIndex = -1
                                                clearPendingMeasure()
                                            }
                                        }

                                        Repeater {
                                            model: csvMeasureModel
                                            delegate: Label {
                                                Layout.fillWidth: true
                                                font.pixelSize: 10
                                                color: csvMeasureSelectedIndex === index ? "#ffeb3b" : "#cfd8dc"
                                                text: "M" + (index + 1) + "  \u0394T=" + (model.deltaText ? model.deltaText : "--")
                                            }
                                        }
                                        Repeater {
                                            model: csvMeasureFModel
                                            delegate: Label {
                                                Layout.fillWidth: true
                                                font.pixelSize: 10
                                                color: csvMeasureFSelectedIndex === index ? "#81d4fa" : "#cfd8dc"
                                                text: "F" + (index + 1) + "  \u0394F=" + (model.deltaText ? model.deltaText : "--")
                                            }
                                        }
                                        Repeater {
                                            model: csvMeasureTFModel
                                            delegate: Label {
                                                Layout.fillWidth: true
                                                font.pixelSize: 10
                                                color: csvMeasureTFSelectedIndex === index ? "#ffd180" : "#cfd8dc"
                                                text: "TF" + (index + 1) + "  \u0394T=" + (model.deltaTextT ? model.deltaTextT : "--") +
                                                      "  \u0394F=" + (model.deltaTextF ? model.deltaTextF : "--")
                                            }
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
                                                checked: csvToolMode === "zoom"
                                                enabled: csvReplay.loaded
                                                onClicked: setCsvTool("zoom")
                                            }
                                            Button {
                                                text: "Reset"
                                                onClicked: {
                                                    resetCsvZoom()
                                                    setCsvTool("mouse")
                                                }
                                            }
                                        }
                                        Label { text: "Drag a rectangle in waterfall to zoom"; font.pixelSize: 10 }
                                        Label { text: "Esc to exit zoom mode"; font.pixelSize: 10 }
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
                    exportIncludeInfo, exportIncludeFreqAxis, exportIncludeTimeAxis,
                    csvFreqMin, csvFreqMax, csvCenterFreq,
                    (csvReplay.loaded ? (csvReplay.timestampAt(0) + " -> " + csvReplay.timestampAt(csvReplay.lineCount - 1)) : "--")
                )
            } else {
                csvReplay.exportWaterfallImageWithMarkers(
                    selectedFile,
                    replaySpectrumModel.dbmMin,
                    replaySpectrumModel.dbmMax,
                    markers, exportIncludeMarkers,
                    exportIncludeInfo, exportIncludeFreqAxis, exportIncludeTimeAxis,
                    csvFreqMin, csvFreqMax, csvCenterFreq,
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
        height: Math.max(420, (parent && parent.height > 0) ? parent.height - 40 : (root.height - 40))
        padding: 10
        standardButtons: Dialog.NoButton

        property bool selecting: false
        property real sx: 0
        property real sy: 0
        property real ex: 0
        property real ey: 0
        property real previewZoomMin: 0.25
        property real previewZoomMax: 6.0
        property real previewZoom: 1.0
        property real pinchLastScale: 1.0
        property int previewAxisLeftWidth: exportIncludeTimeAxis ? 58 : 0
        property int previewAxisBottomHeight: exportIncludeFreqAxis ? 24 : 0

        function setPreviewZoom(v) {
            var z = Math.max(previewZoomMin, Math.min(previewZoomMax, v))
            previewZoom = z
        }

        function surfaceWidthForZoom(z) {
            return Math.max(1, Math.round(csvReplay.exportImageWidth * z)) + previewAxisLeftWidth
        }

        function surfaceHeightForZoom(z) {
            return Math.max(1, Math.round(csvReplay.exportImageHeight * z)) + previewAxisBottomHeight
        }

        function zoomAt(factor, viewX, viewY) {
            if (!(factor > 0.0) || previewFlick.width <= 0 || previewFlick.height <= 0) return

            var oldZoom = previewZoom
            var newZoom = Math.max(previewZoomMin, Math.min(previewZoomMax, oldZoom * factor))
            if (Math.abs(newZoom - oldZoom) < 0.0001) return

            var oldSurfaceW = surfaceWidthForZoom(oldZoom)
            var oldSurfaceH = surfaceHeightForZoom(oldZoom)
            var oldContentW = Math.max(previewFlick.width, oldSurfaceW)
            var oldContentH = Math.max(previewFlick.height, oldSurfaceH)
            var oldSurfaceX = (oldContentW - oldSurfaceW) * 0.5
            var oldSurfaceY = (oldContentH - oldSurfaceH) * 0.5

            var ix = (previewFlick.contentX + viewX - oldSurfaceX) / oldSurfaceW
            var iy = (previewFlick.contentY + viewY - oldSurfaceY) / oldSurfaceH

            previewZoom = newZoom

            var newSurfaceW = surfaceWidthForZoom(newZoom)
            var newSurfaceH = surfaceHeightForZoom(newZoom)
            var newContentW = Math.max(previewFlick.width, newSurfaceW)
            var newContentH = Math.max(previewFlick.height, newSurfaceH)
            var newSurfaceX = (newContentW - newSurfaceW) * 0.5
            var newSurfaceY = (newContentH - newSurfaceH) * 0.5

            var targetX = newSurfaceX + ix * newSurfaceW - viewX
            var targetY = newSurfaceY + iy * newSurfaceH - viewY
            var maxX = Math.max(0, newContentW - previewFlick.width)
            var maxY = Math.max(0, newContentH - previewFlick.height)

            previewFlick.contentX = Math.max(0, Math.min(maxX, targetX))
            previewFlick.contentY = Math.max(0, Math.min(maxY, targetY))
        }

        onOpened: {
            previewZoom = 1.0
        }

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
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 220
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 190
                    Layout.fillHeight: true
                    color: "#f5f5f5"
                    border.color: "#d0d0d0"
                    radius: 4

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8

                        Label {
                            text: "Options d'affichage"
                            font.bold: true
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
                        CheckBox {
                            id: exportFreqAxisCheck
                            Layout.fillWidth: true
                            text: "Axe frequence (bas)"
                            checked: exportIncludeFreqAxis
                            onToggled: exportIncludeFreqAxis = checked
                        }
                        CheckBox {
                            id: exportTimeAxisCheck
                            Layout.fillWidth: true
                            text: "Axe temps (gauche)"
                            checked: exportIncludeTimeAxis
                            onToggled: exportIncludeTimeAxis = checked
                        }
                        Label {
                            text: "Zoom preview"
                            font.bold: true
                            Layout.topMargin: 6
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Button {
                                text: "-"
                                Layout.preferredWidth: 34
                                onClicked: exportPreviewDialog.setPreviewZoom(exportPreviewDialog.previewZoom / 1.25)
                            }
                            Slider {
                                id: previewZoomSlider
                                Layout.fillWidth: true
                                from: exportPreviewDialog.previewZoomMin
                                to: exportPreviewDialog.previewZoomMax
                                stepSize: 0.05
                                value: exportPreviewDialog.previewZoom
                                onMoved: exportPreviewDialog.setPreviewZoom(value)
                                onPressedChanged: {
                                    if (!pressed) {
                                        exportPreviewDialog.setPreviewZoom(value)
                                    }
                                }
                            }
                            Binding { target: previewZoomSlider; property: "value"; value: exportPreviewDialog.previewZoom; when: !previewZoomSlider.pressed }
                            Button {
                                text: "+"
                                Layout.preferredWidth: 34
                                onClicked: exportPreviewDialog.setPreviewZoom(exportPreviewDialog.previewZoom * 1.25)
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            text: Math.round(exportPreviewDialog.previewZoom * 100).toString() + " %"
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                Item {
                    id: previewContainer
                    Layout.fillWidth: true
                    Layout.fillHeight: true
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
                        contentWidth: Math.max(width, previewSurface.width)
                        contentHeight: Math.max(height, previewSurface.height)
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {}
                        ScrollBar.horizontal: ScrollBar {}

                        PinchHandler {
                            id: previewPinch
                            target: null
                            acceptedDevices: PointerDevice.TouchPad | PointerDevice.TouchScreen
                            onActiveChanged: {
                                exportPreviewDialog.pinchLastScale = 1.0
                            }
                            onScaleChanged: {
                                if (!active) return
                                var ratio = scale / exportPreviewDialog.pinchLastScale
                                exportPreviewDialog.pinchLastScale = scale
                                exportPreviewDialog.zoomAt(ratio, centroid.position.x, centroid.position.y)
                            }
                        }

                        WheelHandler {
                            id: previewWheelZoom
                            target: null
                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                            acceptedModifiers: Qt.ControlModifier
                            onWheel: function(event) {
                                var dy = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
                                if (dy === 0) return
                                var factor = dy > 0 ? 1.12 : (1.0 / 1.12)
                                exportPreviewDialog.zoomAt(factor, event.point.position.x, event.point.position.y)
                                event.accepted = true
                            }
                        }

                        Item {
                            id: previewSurface
                            x: (previewFlick.contentWidth - width) / 2
                            y: (previewFlick.contentHeight - height) / 2
                            property int imageWidth: Math.max(1, Math.round(csvReplay.exportImageWidth * exportPreviewDialog.previewZoom))
                            property int imageHeight: Math.max(1, Math.round(csvReplay.exportImageHeight * exportPreviewDialog.previewZoom))
                            property int axisLeftWidth: exportPreviewDialog.previewAxisLeftWidth
                            property int axisBottomHeight: exportPreviewDialog.previewAxisBottomHeight
                            width: imageWidth + axisLeftWidth
                            height: imageHeight + axisBottomHeight

                            Item {
                                id: previewImageArea
                                x: previewSurface.axisLeftWidth
                                y: 0
                                width: previewSurface.imageWidth
                                height: previewSurface.imageHeight

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
                                        property real px: model.xNorm * previewImageArea.width
                                        property real py: csvReplay.lineCount > 1
                                                          ? (1.0 - (model.frameIndex / (csvReplay.lineCount - 1))) * previewImageArea.height
                                                          : (previewImageArea.height * 0.5)
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
                                            x: px + (px > previewImageArea.width * 0.6 ? -width - 6 : 6)
                                            y: py + (py > previewImageArea.height * 0.6 ? -height - 6 : 6)
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
                                    x: exportPreviewDialog.selecting ? Math.min(exportPreviewDialog.sx, exportPreviewDialog.ex) : exportCropX0 * previewImageArea.width
                                    y: exportPreviewDialog.selecting ? Math.min(exportPreviewDialog.sy, exportPreviewDialog.ey) : exportCropY0 * previewImageArea.height
                                    width: exportPreviewDialog.selecting ? Math.abs(exportPreviewDialog.ex - exportPreviewDialog.sx) : (exportCropX1 - exportCropX0) * previewImageArea.width
                                    height: exportPreviewDialog.selecting ? Math.abs(exportPreviewDialog.ey - exportPreviewDialog.sy) : (exportCropY1 - exportCropY0) * previewImageArea.height
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

                            Rectangle {
                                id: exportTimeAxisOverlay
                                visible: exportIncludeTimeAxis
                                x: 0
                                y: 0
                                width: previewSurface.axisLeftWidth
                                height: previewSurface.imageHeight
                                color: "#b0000000"
                                border.color: "#d8d8d8"
                                border.width: 1

                                Repeater {
                                    model: 5
                                    delegate: Item {
                                        property real t: index / 4.0
                                        property real yTick: t * (exportTimeAxisOverlay.height - 1)
                                        property int frameIdx: {
                                            if (!csvReplay.loaded || csvReplay.lineCount <= 1) return 0
                                            return Math.round((csvReplay.lineCount - 1) * (1.0 - t))
                                        }
                                        Rectangle {
                                            x: exportTimeAxisOverlay.width - 6
                                            y: yTick
                                            width: 6
                                            height: 1
                                            color: "#d8d8d8"
                                        }
                                        Text {
                                            x: 3
                                            y: yTick - (height * 0.5)
                                            width: Math.max(8, exportTimeAxisOverlay.width - 9)
                                            horizontalAlignment: Text.AlignRight
                                            color: "white"
                                            font.pixelSize: 9
                                            elide: Text.ElideRight
                                            text: csvReplay.loaded ? shortTimestampLabel(csvReplay.timestampAt(frameIdx)) : "--"
                                        }
                                    }
                                }
                                Text {
                                    id: exportTimeAxisLabel
                                    text: "Time"
                                    color: "white"
                                    font.pixelSize: 8
                                    x: 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    transformOrigin: Item.Center
                                    rotation: -90
                                }
                            }

                            Rectangle {
                                id: exportFreqAxisOverlay
                                visible: exportIncludeFreqAxis
                                x: previewSurface.axisLeftWidth
                                y: previewSurface.imageHeight
                                width: previewSurface.imageWidth
                                height: previewSurface.axisBottomHeight
                                color: "#b0000000"
                                border.color: "#d8d8d8"
                                border.width: 1

                                Repeater {
                                    model: 5
                                    delegate: Item {
                                        property real t: index / 4.0
                                        property real xTick: t * (exportFreqAxisOverlay.width - 1)
                                        property real fMHz: csvFreqMin + t * (csvFreqMax - csvFreqMin)
                                        Rectangle {
                                            x: xTick
                                            y: 0
                                            width: 1
                                            height: 5
                                            color: "#d8d8d8"
                                        }
                                        Text {
                                            y: 4
                                            width: implicitWidth
                                            x: Math.max(1, Math.min(exportFreqAxisOverlay.width - width - 1, xTick - (width * 0.5)))
                                            color: "white"
                                            font.pixelSize: 8
                                            text: fMHz.toFixed(6)
                                        }
                                    }
                                }
                                Text {
                                    text: "MHz"
                                    color: "white"
                                    font.pixelSize: 8
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 1
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
