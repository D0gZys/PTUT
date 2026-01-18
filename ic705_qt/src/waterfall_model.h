#pragma once

#include <QObject>
#include <QImage>
#include <QVector>

class WaterfallModel : public QObject {
    Q_OBJECT
public:
    explicit WaterfallModel(QObject *parent = nullptr);

    const QImage &image() const;
    int width() const;
    int height() const;
    float dbmMin() const;
    float dbmMax() const;

    Q_INVOKABLE void clear();

public slots:
    void pushLine(const QVector<float> &samples);

signals:
    void imageChanged();

private:
    QRgb mapColor(float value) const;

    QImage m_image;
    int m_width;
    int m_height;
    float m_dbmMin;
    float m_dbmMax;
};
