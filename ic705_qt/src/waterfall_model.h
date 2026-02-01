#pragma once

#include <QObject>
#include <QImage>
#include <QVector>

class WaterfallModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(float dbmMin READ dbmMin WRITE setDbmMin NOTIFY rangeChanged)
    Q_PROPERTY(float dbmMax READ dbmMax WRITE setDbmMax NOTIFY rangeChanged)
public:
    explicit WaterfallModel(QObject *parent = nullptr);

    const QImage &image() const;
    int width() const;
    int height() const;
    float dbmMin() const;
    float dbmMax() const;

    Q_INVOKABLE void clear();
    Q_INVOKABLE void setDbmMin(float value);
    Q_INVOKABLE void setDbmMax(float value);
    Q_INVOKABLE void setDbmRange(float minValue, float maxValue);

public slots:
    void pushLine(const QVector<float> &samples);

signals:
    void imageChanged();
    void rangeChanged();

private:
    QRgb mapColor(float value) const;

    QImage m_image;
    int m_width;
    int m_height;
    float m_dbmMin;
    float m_dbmMax;
};
