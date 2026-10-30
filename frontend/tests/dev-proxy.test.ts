// @vitest-environment node
import { createServer as createHttpServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { createServer } from 'vite'
import { expect, it } from 'vitest'
import config from '../vite.config'

it('forwards same-origin API requests without changing the API path', async () => {
  const configuredProxy = config.server?.proxy?.['/api']
  expect(configuredProxy).toMatchObject({ target: 'http://127.0.0.1:8001' })
  expect(config.server).toMatchObject({ port: 5173, strictPort: true })
  if (!configuredProxy || typeof configuredProxy === 'string') throw new Error('Missing API proxy')

  const upstream = createHttpServer((request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ path: request.url }))
  })
  await new Promise<void>(resolve => upstream.listen(0, '127.0.0.1', resolve))
  const upstreamPort = (upstream.address() as AddressInfo).port
  const vite = await createServer({
    ...config,
    configFile: false,
    plugins: [],
    logLevel: 'silent',
    server: {
      ...config.server,
      host: '127.0.0.1',
      port: 0,
      strictPort: false,
      watch: null,
      proxy: { '/api': { ...configuredProxy, target: `http://127.0.0.1:${upstreamPort}` } },
    },
  })
  try {
    await vite.listen()
    const vitePort = (vite.httpServer!.address() as AddressInfo).port
    const response = await fetch(`http://127.0.0.1:${vitePort}/api/batches?probe=1`)

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ path: '/api/batches?probe=1' })
  } finally {
    await vite.close()
    await new Promise<void>((resolve, reject) => upstream.close(error => error ? reject(error) : resolve()))
  }
}, 20000)
