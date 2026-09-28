<template>
  <div>
    <h2 v-if="order.contact.kind === 'business'">Tax invoice</h2>
    <p>{{ order.status }}</p>
  </div>
</template>

<script>
export default {
  props: ['order'],
};
</script>
