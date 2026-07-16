# P3-1 Learnings

## 2026-07-16

- **Ant Design v6 Collapse**: Uses `items` prop (array of `{key, label, children}`). Supports `defaultActiveKey` to control which panels are open by default. The `ghost` prop removes background/border styling.
- **Collapse body rendering**: Children content is NOT rendered in DOM when panel is collapsed (no SSR hidden, just absent). Using `defaultActiveKey` with all keys ensures all content is visible by default while keeping per-panel collapse/expand.
- **`verbatimModuleSyntax: true`**: Requires `import type` for type-only imports. When importing a type used in an interface, it's still a type-only import.
- **api.ts refactoring**: The file was updated to use a `tokenGetter` pattern instead of exporting `getAuth`/`clearAuth` directly. Components now need to access localStorage directly.
- **Test patterns**: vitest 4.x + @testing-library/react works well. Use `container.innerHTML` to verify empty rendering. Use `queryByText` (not `getByText`) to check absence of elements.
