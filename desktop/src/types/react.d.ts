declare module 'react' {
  export type ReactNode = unknown;
  export function StrictMode(props: { children?: ReactNode }): unknown;
  export function useEffect(effect: () => void | (() => void), deps?: unknown[]): void;
  export function useState<T>(
    initial: T | (() => T),
  ): [T, (value: T | ((current: T) => T)) => void];
}

declare module 'react-dom/client' {
  export function createRoot(container: Element): {
    render(node: unknown): void;
  };
}

declare module 'react/jsx-runtime' {
  export const jsx: unknown;
  export const jsxs: unknown;
  export const Fragment: unknown;
}

declare namespace JSX {
  interface IntrinsicElements {
    [key: string]: unknown;
  }
}

declare module '*.css';

interface ImportMetaEnv {
  readonly VITE_RUNTIME_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
