#include "waterfall_item.h"

#include "waterfall_model.h"

#include <QSGSimpleTextureNode>
#include <QSGTexture>

WaterfallItem::WaterfallItem(QQuickItem *parent) : QQuickItem(parent), m_model(nullptr) {
    setFlag(ItemHasContents, true);
}

QObject *WaterfallItem::model() const {
    return m_model;
}

void WaterfallItem::setModel(QObject *model) {
    if (model == m_model) {
        return;
    }
    if (m_model) {
        disconnect(m_model, nullptr, this, nullptr);
    }
    m_model = qobject_cast<WaterfallModel *>(model);
    if (m_model) {
        connect(m_model, &WaterfallModel::imageChanged, this, &WaterfallItem::update);
    }
    emit modelChanged();
    update();
}

QSGNode *WaterfallItem::updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *) {
    QSGSimpleTextureNode *node = static_cast<QSGSimpleTextureNode *>(oldNode);
    if (!node) {
        node = new QSGSimpleTextureNode();
        node->setOwnsTexture(true);
    }

    if (!m_model || !window()) {
        return node;
    }

    const QImage &image = m_model->image();
    if (image.isNull()) {
        return node;
    }

    QSGTexture *texture = window()->createTextureFromImage(image);
    node->setTexture(texture);
    node->setRect(boundingRect());
    node->setFiltering(QSGTexture::Nearest);

    return node;
}
