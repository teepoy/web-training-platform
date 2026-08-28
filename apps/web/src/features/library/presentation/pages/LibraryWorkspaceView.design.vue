<template>
  <main class="library-design">
    <header class="library-header">
      <div>
        <small>DATA RESOURCES</small>
        <h1>Library</h1>
        <p>Find, organize, and create datasets and collections.</p>
      </div>
      <button class="primary">Create ⌄</button>
    </header>

    <nav class="tabs" aria-label="Library resource types">
      <button class="active">Datasets <span>24</span></button>
      <button>Collections <span>6</span></button>
    </nav>

    <section class="resource-panel">
      <div class="shared-query" aria-label="Shared Library filters">
        <label>
          <span>Search current tab</span>
          <input value="surface defects" readonly />
        </label>
        <label>
          <span>Scope</span>
          <select>
            <option>My datasets</option>
            <option>All creators</option>
            <option>Alex Chen</option>
          </select>
        </label>
        <button class="quiet">Clear filters</button>
      </div>
      <div class="advanced-row">
        <strong>Datasets</strong>
        <div>Type · Storage mode · Visibility</div>
      </div>
      <div class="table-placeholder">
        <div>Name</div>
        <div>Dataset type</div>
        <div>View types</div>
        <div>Created</div>
        <div>Actions</div>
      </div>
      <footer>
        <span>24 datasets</span>
        <span>Rows per page: 20 · 1 / 2</span>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.library-design {
  display: grid;
  gap: 18px;
  min-height: 100%;
  padding: 28px;
  color: #20242c;
  background: #f6f7f9;
}

.library-header,
.shared-query,
.tabs,
.advanced-row,
.table-placeholder,
footer {
  display: flex;
  align-items: center;
}

.library-header,
.advanced-row,
footer {
  justify-content: space-between;
}

h1 {
  margin: 4px 0;
  font-size: 28px;
}

p {
  margin: 0;
  color: #6a7280;
}

small {
  color: #5267c9;
  font-weight: 700;
  letter-spacing: 0.12em;
}

button,
input,
select {
  padding: 9px 12px;
  background: white;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}

button.primary {
  color: white;
  background: #5267c9;
}

.shared-query {
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e1e4e9;
}

label {
  display: grid;
  gap: 5px;
  color: #646c79;
  font-size: 12px;
}

label:first-child {
  flex: 1;
}

input {
  width: min(420px, 100%);
}

.tabs {
  gap: 4px;
  border-bottom: 1px solid #dfe3e9;
}

.tabs button {
  border: 0;
  border-radius: 8px 8px 0 0;
}

.tabs button.active {
  color: #4057bd;
  box-shadow: inset 0 -2px #5267c9;
}

.tabs span {
  margin-left: 6px;
  color: #7a8290;
}

.resource-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
  background: white;
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}

.table-placeholder {
  justify-content: space-between;
  min-height: 190px;
  padding: 18px;
  color: #616977;
  background: repeating-linear-gradient(#fff, #fff 42px, #f0f2f5 43px);
  border: 1px solid #e5e8ed;
  border-radius: 8px;
}

footer {
  color: #747c89;
  font-size: 12px;
}

@media (max-width: 680px) {
  .library-design {
    padding: 16px;
  }

  .library-header,
  .shared-query {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
