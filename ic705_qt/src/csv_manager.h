#pragma once

#include <QObject>
#include <QStringList>
#include <QVariantList>
#include <QDateTime>

class CsvManager : public QObject {
    Q_OBJECT

public:
    explicit CsvManager(QObject *parent = nullptr);

    // Scan recent CSV files from recep_csv folder
    Q_INVOKABLE QVariantList scanRecentFiles(const QString &basePath, int maxFiles = 50);
    
    // Get max dBm value from a specific index in loaded CSV
    Q_INVOKABLE double getMaxDbmAtIndex(int index) const;
    
    // Find index with maximum signal across entire CSV
    Q_INVOKABLE int findMaxSignalIndex() const;
    
    // Export waterfall + spectrum to image/PDF
    Q_INVOKABLE bool exportReport(const QString &filePath, 
                                   const QString &format,
                                   bool includeSpectrum,
                                   bool includeWaterfall,
                                   bool includeStats,
                                   bool includeMarkers);

signals:
    void scanProgress(int current, int total);
    void exportProgress(int percent);

private:
    struct CsvFileInfo {
        QString fileName;
        QString filePath;
        QDateTime date;
        int lineCount;
        double freqMHz;
        double maxDbm;
    };

    CsvFileInfo parseCsvFile(const QString &filePath) const;
    QStringList findCsvFiles(const QString &basePath) const;
    double extractMaxDbmFromFilename(const QString &fileName) const;
};
