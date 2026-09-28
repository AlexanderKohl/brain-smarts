// A role is read as user.role but set as updates.role: the same name under another path.
function canRefund(req) {
  return req.user.role === 'manager';
}

function promote(updates) {
  updates.role = 'manager';
  return updates;
}

module.exports = { canRefund, promote };
