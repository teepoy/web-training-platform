<template>
  <section class="prediction-export-tab-design">
    <header>
      <small>EXPORT</small>
      <h2>Export current results</h2>
      <p>Build a downstream artifact from the Dataset's current classification result.</p>
    </header>

    <div class="result-source">
      <div>
        <strong>Exported class</strong>
        <span>Choose Annotation, Prediction, or Final Class.</span>
      </div>
      <div class="source-options">
        <button>Annotation</button><button>Prediction</button
        ><button class="selected">Final Class</button>
      </div>
    </div>

    <div class="distribution">
      <strong>Final Class distribution</strong>
      <span>60 · 4,850 · 48.5%</span><span>61 · 3,100 · 31%</span><span>0 · 2,050 · 20.5%</span>
    </div>

    <div class="formats">
      <button><strong>Parquet</strong><span>Analytics-ready rows</span></button>
      <button class="selected"><strong>KLARF</strong><span>Wafer defect result</span></button>
      <button><strong>ZIP package</strong><span>Parquet, KLARF, and manifest</span></button>
    </div>

    <div class="klarf-version">
      <div><strong>KLARF version</strong><span>Applied to each numbered KLARF file</span></div>
      <div class="version-options"><button class="selected">1.2</button><button>1.8</button></div>
    </div>

    <div class="image-export">
      <div>
        <strong>Include defect images</strong>
        <span>One defective patch per row retained after Review Sampling</span>
      </div>
      <button>Off</button>
    </div>

    <div class="sampling">
      <div><strong>Review Sampling</strong><span>Optional · ordered 17-rule pipeline</span></div>
      <button>Configure</button>
    </div>

    <div class="large-export-note">
      <strong>Large exports may take several minutes</strong>
      <span>Progress stays live; downloads stream in resumable byte ranges.</span>
    </div>

    <footer><button class="primary">Create export</button></footer>
  </section>
</template>

<style scoped>
.prediction-export-tab-design {
  display: grid;
  gap: 18px;
  max-width: 980px;
  padding: 24px 0;
  color: #20242c;
}
header h2,
header p {
  margin: 4px 0 0;
}
header p,
.klarf-version span,
.image-export span,
.sampling span {
  color: #687180;
}
small {
  color: #5267c9;
  font-weight: 700;
  letter-spacing: 0.12em;
}
.result-source,
.distribution,
.klarf-version,
.image-export,
.sampling,
.large-export-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  background: #f5f7fb;
  border: 1px solid #dfe3e9;
  border-radius: 10px;
}
.large-export-note {
  display: grid;
  justify-content: stretch;
  color: #7c5013;
  background: #fff8e6;
  border-color: #f0d29a;
}
.result-source span,
.distribution span {
  color: #394a9b;
}
.source-options,
.distribution {
  display: flex;
  align-items: center;
  gap: 8px;
}
.formats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
button {
  padding: 12px;
  text-align: left;
  background: #fff;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}
.formats button {
  min-height: 96px;
}
.formats strong,
.formats span,
.klarf-version strong,
.klarf-version span,
.image-export strong,
.image-export span,
.sampling strong,
.sampling span {
  display: block;
}
.formats span,
.klarf-version span,
.image-export span,
.sampling span {
  margin-top: 5px;
}
.selected {
  background: #f2f5ff;
  box-shadow: inset 0 0 0 1px #5267c9;
}
.version-options {
  display: flex;
  gap: 6px;
}
footer {
  display: flex;
  justify-content: flex-end;
}
.primary {
  color: #fff;
  background: #5267c9;
}
</style>
