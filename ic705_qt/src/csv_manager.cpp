#include "csv_manager.h"
#include <QDir>
#include <QFile>
#include <QTextStream>
#include <QRegularExpression>
#include <QDebug>
#include <algorithm>

CsvManager::CsvManager(QObject *parent)
    : QObject(parent)
{
}

QVariantList CsvManager::scanRecentFiles(const QString &basePath, int maxFiles)
{
    QVariantList result;
    
    QDir baseDir(basePath);
    if (!baseDir.exists()) {
        qWarning() << "CSV folder does not exist:" << basePath;
        return result;
    }

    QStringList csvFiles = findCsvFiles(basePath);
    
    // Sort by date (newest first)
    std::sort(csvFiles.begin(), csvFiles.end(), std::greater<QString>());
    
    int count = 0;
    for (const QString &filePath : csvFiles) {
        if (count >= maxFiles) break;
        
        CsvFileInfo info = parseCsvFile(filePath);
        
        QVariantMap fileData;
        fileData["fileName"] = info.fileName;
        fileData["filePath"] = info.filePath;
        fileData["date"] = info.date.toString("yyyy-MM-dd HH:mm");
        fileData["lines"] = QString::number(info.lineCount);
        fileData["freq"] = QString::number(info.freqMHz, 'f', 3) + " MHz";
        fileData["maxDbm"] = info.maxDbm != 0.0 ? QString::number(info.maxDbm, 'f', 1) : "";
        
        result.append(fileData);
        count++;
        
        emit scanProgress(count, csvFiles.size());
    }
    
    return result;
}

double CsvManager::getMaxDbmAtIndex(int index) const
{
    // TODO: Implement when CSV replay model exposes current frame data
    return -100.0;
}

int CsvManager::findMaxSignalIndex() const
{
    // TODO: Implement by scanning all frames in loaded CSV
    // This requires access to CsvReplay's m_frames
    return 0;
}

bool CsvManager::exportReport(const QString &filePath,
                               const QString &format,
                               bool includeSpectrum,
                               bool includeWaterfall,
                               bool includeStats,
                               bool includeMarkers)
{
    qInfo() << "Export report:" << filePath << format;
    qInfo() << "  Spectrum:" << includeSpectrum;
    qInfo() << "  Waterfall:" << includeWaterfall;
    qInfo() << "  Stats:" << includeStats;
    qInfo() << "  Markers:" << includeMarkers;
    
    // TODO: Implement using QPainter / QImage / QPdfWriter
    // 1. Create QImage with appropriate size
    // 2. Draw waterfall using WaterfallModel data
    // 3. Draw spectrum using SpectrumModel data
    // 4. Add text annotations (stats, markers)
    // 5. Save to PNG/JPG or generate PDF
    
    emit exportProgress(100);
    return false; // Not implemented yet
}

CsvManager::CsvFileInfo CsvManager::parseCsvFile(const QString &filePath) const
{
    CsvFileInfo info;
    info.filePath = filePath;
    info.fileName = QFileInfo(filePath).fileName();
    info.date = QFileInfo(filePath).lastModified();
    info.lineCount = 0;
    info.freqMHz = 0.0;
    info.maxDbm = extractMaxDbmFromFilename(info.fileName);

    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return info;
    }

    QTextStream in(&file);
    bool firstLine = true;
    
    while (!in.atEnd()) {
        QString line = in.readLine();
        
        if (firstLine) {
            firstLine = false;
            // Skip header
            continue;
        }
        
        info.lineCount++;
        
        // Parse first data line to get frequency
        if (info.lineCount == 1) {
            QStringList fields = line.split(',');
            if (fields.size() > 1) {
                bool ok;
                double freq = fields[1].toDouble(&ok);
                if (ok) {
                    info.freqMHz = freq;
                }
            }
        }
    }
    
    file.close();
    return info;
}

QStringList CsvManager::findCsvFiles(const QString &basePath) const
{
    QStringList result;
    
    QDir baseDir(basePath);
    
    // Get all date folders (YYYYMMDD)
    QStringList dateFolders = baseDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot);
    
    for (const QString &dateFolder : dateFolders) {
        QDir subDir(basePath + "/" + dateFolder);
        QStringList csvFiles = subDir.entryList(QStringList() << "*.csv", QDir::Files);
        
        for (const QString &csvFile : csvFiles) {
            result.append(subDir.absoluteFilePath(csvFile));
        }
    }
    
    return result;
}

double CsvManager::extractMaxDbmFromFilename(const QString &fileName) const
{
    // Extract from filename like: trigger_-130dBm_143215_max-95dBm.csv
    QRegularExpression re("max(-?\\d+(?:\\.\\d+)?)dBm");
    QRegularExpressionMatch match = re.match(fileName);
    
    if (match.hasMatch()) {
        bool ok;
        double value = match.captured(1).toDouble(&ok);
        if (ok) {
            return value;
        }
    }
    
    return 0.0;
}
