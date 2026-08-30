<template>
  <main class="collection-classify-design">
    <header>
      <div class="context-row">
        <button>← Collection</button>
        <div class="context-copy">
          <strong>Collection name / Active dataset</strong>
          <span>Revision r3 · 3 datasets combined</span>
        </div>
        <button>Handbook</button>
      </div>
      <div class="action-row">
        <div>Filters · Random filter</div>
        <div>Trainer selector · Train &amp; Predict · View task</div>
      </div>
      <div class="status-row">Workflow status and training-limit notices appear here.</div>
    </header>
    <section class="workspace">Map, sample table, and annotation workspace</section>
  </main>
</template>

<style scoped>
.collection-classify-design {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 12px;
  min-height: 100%;
  padding: 16px;
  color: #edf0f5;
  background: #12151c;
}

header {
  display: grid;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid #343a46;
}

.context-row,
.action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.context-copy {
  display: grid;
  flex: 1;
  gap: 3px;
}

.context-copy span,
.status-row {
  color: #9ea6b5;
  font-size: 12px;
}

button {
  padding: 7px 10px;
  color: inherit;
  background: #202631;
  border: 1px solid #3d4553;
  border-radius: 7px;
}

.action-row {
  padding: 10px 12px;
  background: #1a1f28;
  border-radius: 9px;
}

.workspace {
  display: grid;
  place-items: center;
  min-height: 520px;
  background: #171b23;
  border: 1px solid #303642;
  border-radius: 10px;
}
</style>
