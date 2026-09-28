// Fictional shop backend used by the code-map tests.
const express = require('express');
const orders = require('./routes/orders');
const { helper } = require('./lib/a');

const app = express();
app.use(express.json());
app.use('/api', orders);

const port = process.env.PORT || 3000;
const secret = process.env.SHOP_SECRET;

app.listen(port, () => helper(secret));

module.exports = app;
