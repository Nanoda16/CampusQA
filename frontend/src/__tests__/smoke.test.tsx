import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

/** 一个不依赖外部模块的极简组件，用于烟雾测试 */
function HelloWorld() {
  return <h1>Hello, World!</h1>
}

describe('smoke test', () => {
  it('renders a basic component', () => {
    render(<HelloWorld />)
    expect(screen.getByText('Hello, World!')).toBeDefined()
  })

  it('vitest environment is jsdom', () => {
    expect(typeof window).toBe('object')
    expect(typeof document).toBe('object')
  })
})
