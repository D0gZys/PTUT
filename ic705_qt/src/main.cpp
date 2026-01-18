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

    SpectrumModel spectrumModel;
    spectrumModel.start();
    WaterfallModel waterfallModel;
    bool waterfallAuto = true;
    QObject::connect(&spectrumModel, &SpectrumModel::samplesChanged, &waterfallModel,
                     [&waterfallModel, &spectrumModel, &waterfallAuto]() {
                         if (waterfallAuto) {
                             waterfallModel.pushLine(spectrumModel.samples());
                         }
                     });
    CivClient civClient;
    CsvReplay csvReplay;
    bool liveActive = false;
    bool replayActive = false;
    QObject::connect(&civClient, &CivClient::spectrumReady, &spectrumModel,
                     [&spectrumModel, &liveActive, &replayActive](const QVector<float> &samples) {
                         if (replayActive) {
                            return;
                         }
                         spectrumModel.setSamples(samples);
                         if (!liveActive) {
                             spectrumModel.stop();
                             liveActive = true;
                         }
                     });
    QObject::connect(&civClient, &CivClient::connectedChanged, &spectrumModel,
                     [&civClient, &spectrumModel, &liveActive, &replayActive]() {
                         if (!civClient.connected()) {
                             liveActive = false;
                             if (!replayActive) {
                                 spectrumModel.start();
                             }
                         }
                     });
    QObject::connect(&csvReplay, &CsvReplay::frameReady, &spectrumModel,
                     [&spectrumModel, &waterfallModel, &replayActive](const QVector<float> &samples) {
                         spectrumModel.setSamples(samples);
                         if (replayActive) {
                             waterfallModel.pushLine(samples);
                         }
                     });
    QObject::connect(&csvReplay, &CsvReplay::historyReady, &waterfallModel,
                     [&spectrumModel, &waterfallModel](const QVector<QVector<float>> &frames) {
                         waterfallModel.clear();
                         for (const auto &frame : frames) {
                             waterfallModel.pushLine(frame);
                         }
                         if (!frames.isEmpty()) {
                             spectrumModel.setSamples(frames.last());
                         }
                     });
    QObject::connect(&csvReplay, &CsvReplay::loadedChanged, &spectrumModel,
                     [&csvReplay, &spectrumModel, &waterfallModel, &replayActive, &waterfallAuto]() {
                         replayActive = csvReplay.loaded();
                         waterfallAuto = !replayActive;
                         if (replayActive) {
                             spectrumModel.stop();
                             waterfallModel.clear();
                         } else {
                             spectrumModel.start();
                         }
                     });

    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::warnings, &engine,
                     [](const QList<QQmlError> &warnings) {
                         for (const auto &w : warnings) {
                             qWarning().noquote() << w.toString();
                         }
                     });
    engine.rootContext()->setContextProperty("spectrumModel", &spectrumModel);
    engine.rootContext()->setContextProperty("waterfallModel", &waterfallModel);
    engine.rootContext()->setContextProperty("civClient", &civClient);
    engine.rootContext()->setContextProperty("csvReplay", &csvReplay);
    engine.loadFromModule("IC705", "Main");
    if (engine.rootObjects().isEmpty()) {
        qCritical() << "Failed to load QML.";
        return -1;
    }

    return app.exec();
}
