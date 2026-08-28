<template>
  <main class="history-design">
    <header>
      <div>
        <small>ACTIVITY</small>
        <h1>Training jobs</h1>
      </div>
      <button>Start new job</button>
    </header>
    <section class="toolbar">
      <input placeholder="Search jobs" />
      <select>
        <option>All statuses</option>
      </select>
      <select>
        <option>All creators</option>
      </select>
    </section>
    <section class="table">Server-filtered results · 20 rows per page</section>
  </main>
</template>
<style scoped>
.history-design {
  display: grid;
  gap: 18px;
  padding: 28px;
  background: #f6f7f9;
}
header,
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
h1 {
  margin: 4px 0;
}
small {
  color: #5267c9;
  font-weight: 700;
}
input,
select,
button {
  padding: 9px 12px;
  background: white;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}
.toolbar input {
  flex: 1;
}
.table {
  min-height: 220px;
  padding: 18px;
  background: white;
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}
</style>
