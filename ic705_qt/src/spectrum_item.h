#pragma once

#include <QQuickItem>

class SpectrumModel;

class SpectrumItem : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(QObject *model READ model WRITE setModel NOTIFY modelChanged)
public:
    explicit SpectrumItem(QQuickItem *parent = nullptr);

    QObject *model() const;
    void setModel(QObject *model);

signals:
    void modelChanged();

protected:
    QSGNode *updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *data) override;

private:
    SpectrumModel *m_model;
};
