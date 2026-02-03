#include <QGuiApplication>
#include <QDateTime>
#include <QFile>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlError>
#include <QTextStream>
#include <QUrl>

#include "spectrum_item.h"
#include "spectrum_model.h"
#include "waterfall_item.h"
#include "waterfall_model.h"
#include "civ_client.h"
#include "csv_replay.h"
#include "csv_recorder.h"
#include "csv_manager.h"

namespace {
QFile g_logFile;

QString msgTypeToString(QtMsgType type) {
    switch (type) {
    case QtDebugMsg:
        return "DBG";
    case QtInfoMsg:
        return "INF";
    case QtWarningMsg:
        return "WRN";
    case QtCriticalMsg:
        return "CRT";
    case QtFatalMsg:
        return "FTL";
    }
    return "UNK";
}

void fileMessageHandler(QtMsgType type, const QMessageLogContext &, const QString &msg) {
    if (!g_logFile.isOpen()) {
        return;
    }
    QTextStream ts(&g_logFile);
    ts << QDateTime::currentDateTime().toString(Qt::ISODateWithMs) << " " << msgTypeToString(type)
       << " " << msg << "\n";
    ts.flush();
}

void openLogFile(const QString &path) {
    if (g_logFile.isOpen()) {
        return;
    }
    g_logFile.setFileName(path);
    if (g_logFile.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        qInstallMessageHandler(fileMessageHandler);
        qInfo().noquote() << "Logging to" << path;
    }
}
} // namespace

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);

    openLogFile(QCoreApplication::applicationDirPath() + "/ic705_qt_run.log");
    qInfo().noquote() << "App dir:" << QCoreApplication::applicationDirPath();

    qmlRegisterType<SpectrumItem>("IC705", 1, 0, "SpectrumItem");
    qmlRegisterType<WaterfallItem>("IC705", 1, 0, "WaterfallItem");

    SpectrumModel liveSpectrumModel;
    liveSpectrumModel.start();
    WaterfallModel liveWaterfallModel;
    QObject::connect(&liveSpectrumModel, &SpectrumModel::samplesChanged, &liveWaterfallModel,
                     [&liveWaterfallModel, &liveSpectrumModel]() {
                         liveWaterfallModel.pushLine(liveSpectrumModel.samples());
                     });

    SpectrumModel replaySpectrumModel;
    WaterfallModel replayWaterfallModel;

    CivClient civClient;
    CsvReplay csvReplay;
    CsvRecorder csvRecorder;
    CsvManager csvManager;
    bool liveActive = false;

    QObject::connect(&civClient, &CivClient::spectrumReady, &liveSpectrumModel,
                     [&liveSpectrumModel, &liveActive](const QVector<float> &samples) {
                         liveSpectrumModel.setSamples(samples);
                         if (!liveActive) {
                             liveSpectrumModel.stop();
                             liveActive = true;
                         }
                     });
    QObject::connect(&civClient, &CivClient::spectrumReady, &csvRecorder,
                     [&csvRecorder](const QVector<float> &samples) {
                         csvRecorder.pushSamples(samples);
                     });
    QObject::connect(&civClient, &CivClient::connectedChanged, &liveSpectrumModel,
                     [&civClient, &liveSpectrumModel, &liveActive]() {
                         if (!civClient.connected()) {
                             liveActive = false;
                             liveSpectrumModel.start();
                         }
                     });
    QObject::connect(&civClient, &CivClient::freqChanged, &csvRecorder,
                     [&civClient, &csvRecorder]() {
                         csvRecorder.setCurrentFreqMHz(civClient.freqMHz());
                     });
    QObject::connect(&civClient, &CivClient::refLevelChanged, &csvRecorder,
                     [&civClient, &csvRecorder]() {
                         csvRecorder.setRefLevel(civClient.refLevel());
                     });
    QObject::connect(&csvReplay, &CsvReplay::frameReady, &replaySpectrumModel,
                     [&replaySpectrumModel, &replayWaterfallModel](const QVector<float> &samples) {
                         replaySpectrumModel.setSamples(samples);
                         replayWaterfallModel.pushLine(samples);
                     });
    QObject::connect(&csvReplay, &CsvReplay::historyReady, &replayWaterfallModel,
                     [&replaySpectrumModel, &replayWaterfallModel](const QVector<QVector<float>> &frames) {
                         replayWaterfallModel.clear();
                         for (const auto &frame : frames) {
                             replayWaterfallModel.pushLine(frame);
                         }
                         if (!frames.isEmpty()) {
                             replaySpectrumModel.setSamples(frames.last());
                         }
                     });
    QObject::connect(&csvReplay, &CsvReplay::loadedChanged, &replayWaterfallModel,
                     [&csvReplay, &replayWaterfallModel]() {
                         if (!csvReplay.loaded()) {
                             replayWaterfallModel.clear();
                         }
                     });

    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::warnings, &engine,
                     [](const QList<QQmlError> &warnings) {
                         for (const auto &w : warnings) {
                             qWarning().noquote() << w.toString();
                         }
                     });
    engine.rootContext()->setContextProperty("liveSpectrumModel", &liveSpectrumModel);
    engine.rootContext()->setContextProperty("liveWaterfallModel", &liveWaterfallModel);
    engine.rootContext()->setContextProperty("replaySpectrumModel", &replaySpectrumModel);
    engine.rootContext()->setContextProperty("replayWaterfallModel", &replayWaterfallModel);
    engine.rootContext()->setContextProperty("civClient", &civClient);
    engine.rootContext()->setContextProperty("csvReplay", &csvReplay);
    engine.rootContext()->setContextProperty("csvRecorder", &csvRecorder);
    engine.rootContext()->setContextProperty("csvManager", &csvManager);
    engine.loadFromModule("IC705", "Main");
    if (engine.rootObjects().isEmpty()) {
        qCritical() << "Failed to load QML.";
        return -1;
    }

    return app.exec();
}
