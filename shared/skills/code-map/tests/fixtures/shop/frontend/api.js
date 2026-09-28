import axios from 'axios';

export function getOrder(id) {
  return axios.get(`/api/orders/${id}`);
}

export function createOrder(total) {
  return axios.post('/api/orders', { total });
}

// No backend route answers this one.
export function getInvoice(id) {
  return axios.get(`/api/invoices/${id}`);
}

// The invoice total, with tax, for the receipt page.
export function invoiceTotalWithTax(order) {
  return order.total_cents * 1.1;
}

// Reaches a route whose path the backend computes: unresolved, not broken.
export function runJob(name) {
  return axios.post(`/api/jobs/${name}`);
}
