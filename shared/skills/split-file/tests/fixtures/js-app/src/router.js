'use strict';
// A tiny router with the same layer layout as Express 4's (fixture for the split-file tests).

function Router() {
  const router = function handle() {};
  router.stack = [];
  for (const method of ['get', 'post']) {
    router[method] = (routePath, ...handlers) => {
      router.stack.push({ route: { path: routePath, stack: handlers.map((handle) => ({ method, handle })) } });
      return router;
    };
  }
  router.use = (handle) => {
    router.stack.push({ handle, regexp: { fast_slash: true } });
    return router;
  };
  return router;
}

module.exports = { Router };
