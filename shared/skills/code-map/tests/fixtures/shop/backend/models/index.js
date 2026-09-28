const { Sequelize, DataTypes } = require('sequelize');

const sequelize = new Sequelize('sqlite::memory:');

const Order = sequelize.define('Order', {
  status: { type: DataTypes.STRING },
  total_cents: { type: DataTypes.INTEGER },
}, { tableName: 'orders', underscored: true });

module.exports = { Order, sequelize };
