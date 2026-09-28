const express = require('express');
const { Order } = require('../models');

const router = express.Router();

router.get('/orders/:id', async (req, res) => {
  const order = await Order.findOne({ where: { id: req.params.id, status: 'open' } });
  const label = order.total_cents > 0 ? 'paid' : 'free';
  const kind = order.contact.kind || 'person';
  if (order.contact.kind === 'business') res.set('X-Tax', 'included');
  res.json({ order, label, customerKind: kind });
});

router.post('/orders', async (req, res) => {
  const order = await Order.create({ status: 'open', total_cents: req.body.total });
  res.json(order);
});

router.get('/orders', async (req, res) => {
  // customer_ref is not an attribute of Order: the columns check must say so.
  const list = await Order.findAll({ where: { customer_ref: req.query.ref } });
  res.json(list);
});

module.exports = router;
