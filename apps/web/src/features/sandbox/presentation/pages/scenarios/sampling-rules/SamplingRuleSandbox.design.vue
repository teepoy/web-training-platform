<template>
  <main class="rule-builder-design">
    <header>
      <div>
        <small>SAMPLING LAB</small>
        <h1>Sampling rule builder</h1>
      </div>
      <button>Run preview</button>
    </header>
    <section class="pipeline">
      Extra filter → Conditional limit → Group quota → Total limit → Random draw
    </section>
    <section class="workspace">
      <aside class="catalog">Five rule types</aside>
      <article class="editor">Active rule configuration</article>
      <aside class="preview">Stage and distribution preview</aside>
    </section>
  </main>
</template>

<style scoped>
.rule-builder-design {
  min-height: 100%;
  padding: 28px;
  color: #17221d;
  background: #f3f6f2;
}

header,
.workspace {
  display: flex;
  gap: 18px;
}

header {
  align-items: center;
  justify-content: space-between;
}

h1 {
  margin: 4px 0 18px;
}

small {
  color: #397457;
  font-weight: 700;
  letter-spacing: 0.14em;
}

button {
  padding: 10px 18px;
  color: white;
  background: #22684c;
  border: 0;
  border-radius: 10px;
}

.pipeline,
.catalog,
.editor,
.preview {
  padding: 20px;
  background: white;
  border: 1px solid #dfe5df;
  border-radius: 16px;
}

.pipeline {
  margin-bottom: 18px;
  background: #dfece3;
}

.catalog {
  width: 23%;
}

.editor {
  flex: 1;
  min-height: 560px;
}

.preview {
  width: 28%;
}
</style>
