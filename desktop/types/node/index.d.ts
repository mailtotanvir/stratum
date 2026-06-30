declare namespace NodeJS {
  interface ProcessEnv {
    [key: string]: string | undefined;
  }

  class EventEmitter<T = any> {}
}

declare interface Buffer {}

declare interface BufferConstructor {
  from(value: unknown): Buffer;
  new (...args: unknown[]): Buffer;
}

declare const Buffer: BufferConstructor;

declare const process: {
  env: NodeJS.ProcessEnv;
};

declare module 'node:http' {
  export class IncomingMessage {
    url?: string | undefined;
  }
  export class ServerResponse {}
  export class Agent {}
  export class ClientRequest {}
  export interface ClientRequestArgs {
    [key: string]: unknown;
  }
  export interface OutgoingHttpHeaders {
    [key: string]: string | string[] | number | undefined;
  }
  export class Server {}
  export interface ServerOptions {
    [key: string]: unknown;
  }
  export interface RequestOptions extends ClientRequestArgs {}
  export class Http2SecureServer {}
}

declare module 'node:https' {
  export class Agent {}
  export interface RequestOptions {
    [key: string]: unknown;
  }
  export class Server {}
  export interface ServerOptions {
    [key: string]: unknown;
  }
}

declare module 'node:net' {
  export class Server {}
  export class Socket {}
  export interface AddressInfo {
    address: string;
    family: string;
    port: number;
  }
}

declare module 'node:fs' {
  export interface FSWatcher {}
  export interface Stats {}
  export interface ReadStream {}
  export interface WriteStream {}
  export type PathLike = string;
}

declare module 'node:stream' {
  export class Stream {}
  export class Duplex {}
  export interface DuplexOptions {
    [key: string]: unknown;
  }
  export class Readable {}
  export class Writable {}
}

declare module 'node:zlib' {
  export interface ZlibOptions {
    [key: string]: unknown;
  }
}

declare module 'node:tls' {
  export interface SecureContextOptions {
    [key: string]: unknown;
  }
}

declare module 'node:events' {
  export class EventEmitter<T = any> {}
}

declare module 'node:url' {
  export class URL {
    constructor(input: string | URL, base?: string | URL);
  }
}

declare module 'node:*' {
  export * from 'node:http';
}
