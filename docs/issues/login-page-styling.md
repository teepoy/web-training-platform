# Login Page Styling Issue

## Status
**Unresolved**

## Problem
The login page input fields have a pure white background color despite Naive UI dark theme CSS variables being applied correctly.

## Symptoms
- Input elements (`<input class="n-input__input-el">`) show white background
- Naive UI CSS variables are present and correct (e.g., `--n-color: rgba(255, 255, 255, 0.1)`)
- The dark theme is being applied to the `n-config-provider`
- The white background appears to override the theme styling

## Example DOM Structure
```html
<div class="n-input n-input--medium-size n-input--resizable n-input--stateful" 
     style="--n-color: rgba(255, 255, 255, 0.1); ...">
  <div class="n-input-wrapper">
    <div class="n-input__input">
      <input type="text" class="n-input__input-el" placeholder="you@example.com" size="20">
    </div>
  </div>
</div>
```

The `n-input` div has correct dark theme variables, but the inner `input` element has a pure white background.

## Attempted Fixes
1. Added global CSS reset with `background: transparent !important` on `.n-input__input-el`
2. Reset input/textarea/select/button to use `background: inherit`
3. Force dark theme on auth pages in App.vue

None of these resolved the issue.

## Relevant Files
- [`apps/web/src/views/LoginView.vue`](../../apps/web/src/views/LoginView.vue) - Login page component
- [`apps/web/src/views/RegisterView.vue`](../../apps/web/src/views/RegisterView.vue) - Register page (likely same issue)
- [`apps/web/src/style.css`](../../apps/web/src/style.css) - Global styles with attempted fixes
- [`apps/web/src/App.vue`](../../apps/web/src/App.vue) - Theme provider setup

## Possible Causes to Investigate
1. CSS specificity - Naive UI styles may load after global styles
2. Browser autofill styles overriding input backgrounds
3. Naive UI version compatibility issue
4. Missing CSS import or bundling issue
5. CSS-in-JS injection order

## Environment
- Naive UI v2.44.1
- Vue 3 + Vite
- Using `unplugin-vue-components` with `NaiveUiResolver`
