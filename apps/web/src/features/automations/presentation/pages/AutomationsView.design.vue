<template>
  <main class="automation-design">
    <header>
      <div>
        <h1>Automations</h1>
        <p>Cross-Collection monitoring only; configuration stays with each Collection.</p>
      </div>
      <button>Refresh</button>
    </header>
    <aside>Plain-language explanation and recovery guidance</aside>
    <section class="filters">Search · Status · Work type</section>
    <section class="table">
      <div>Collection</div>
      <div>Work</div>
      <div>Status</div>
      <div>Started</div>
      <div>Finished</div>
      <div>Recovery</div>
    </section>
  </main>
</template>

<style scoped>
.automation-design {
  display: grid;
  gap: 16px;
  padding: 24px;
}

header,
.filters,
.table {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

aside,
.filters,
.table {
  border: 1px solid #d8dee8;
  border-radius: 10px;
  padding: 16px;
}

.table > div {
  flex: 1;
}
</style>
