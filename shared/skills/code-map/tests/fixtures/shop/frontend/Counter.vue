<template>
  <button ref="button" @click="count++">{{ count }} {{ label }}</button>
  <ul><li v-for="row in rows" :key="row.id">{{ row.id }}</li></ul>
  <!-- <p>{{ hiddenNote }}</p> -->
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({ label: String });
const count = ref(0);
const button = ref(null);
let nextId = 0;
const rows = [{ id: nextId++ }, { id: nextId++ }];
const unusedLabel = ref('never shown');
const hiddenNote = ref('only in a comment');
const draft = ref('');
function reset() {
  draft.value = '';
}
</script>
