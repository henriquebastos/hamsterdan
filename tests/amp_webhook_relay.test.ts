import { afterEach, describe, expect, test } from 'bun:test'
import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import plugin, { forwardToApplication } from '../.amp/plugins/github-webhook-relay'

const DELIVERY = '12345678-1234-4234-8234-123456789abc'
const BODY = new Uint8Array([0, 255, 123, 10, 32, 125])
const HEADERS = {
	'content-type': 'application/json',
	'x-github-delivery': DELIVERY,
	'x-github-event': 'pull_request',
	'x-hub-signature-256': 'sha256=sensitive-signature',
}
const event = { body: BODY, headers: HEADERS }
const temporaryDirectories: string[] = []

function privateRelayPath(): string {
	const directory = mkdtempSync(join(tmpdir(), 'hamsterdan-relay-test-'))
	temporaryDirectories.push(directory)
	const path = join(directory, 'relay.json')
	process.env.HAMSTERDAN_RELAY_FILE = path
	return path
}

function receipt(disposition: 'accepted' | 'accepted_terminal' | 'duplicate', deliveryID = DELIVERY) {
	return new Response(JSON.stringify({ custody: 'durable', delivery_id: deliveryID, disposition }), {
		status: 202,
		headers: { 'content-type': 'application/json' },
	})
}

afterEach(() => {
	delete process.env.HAMSTERDAN_RELAY_FILE
	for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true })
})

describe('Hamsterdan Amp GitHub webhook relay', () => {
	test('registers one stable webhook with only the four required headers', async () => {
		const relayPath = privateRelayPath()
		const registrations: unknown[] = []
		await plugin({
			createWebhook: async (options: unknown) => {
				registrations.push(options)
				return { url: 'https://sensitive-capability.example' }
			},
		} as never)

		expect(registrations).toHaveLength(1)
		const registration = registrations[0] as { key: string; headers: string[]; handler: unknown }
		expect(registration.key).toBe('hamsterdan-github')
		expect(registration.headers).toEqual([
			'content-type',
			'x-hub-signature-256',
			'x-github-event',
			'x-github-delivery',
		])
		expect(typeof registration.handler).toBe('function')
		expect(statSync(dirname(relayPath)).mode & 0o777).toBe(0o700)
		expect(statSync(relayPath).mode & 0o777).toBe(0o600)
		expect(JSON.parse(readFileSync(relayPath, 'utf8'))).toEqual({
			key: 'hamsterdan-github',
			url: 'https://sensitive-capability.example',
		})
	})

	test('forwards exact bytes and only allowlisted headers to literal loopback', async () => {
		let request: { input: string; init: RequestInit } | undefined
		await forwardToApplication(event, new AbortController().signal, async (input, init) => {
			request = { input: String(input), init: init! }
			return receipt('accepted')
		})

		expect(request?.input).toBe('http://127.0.0.1:8000/github/webhooks')
		expect(request?.init.method).toBe('POST')
		expect(request?.init.body).toBe(BODY)
		expect(request?.init.headers).toEqual(HEADERS)
	})

	test.each(['accepted', 'accepted_terminal', 'duplicate'] as const)(
		'accepts proven %s durable custody',
		async (disposition) => {
			await expect(
				forwardToApplication(event, new AbortController().signal, async () => receipt(disposition)),
			).resolves.toBeUndefined()
		},
	)

	test('rejects mismatched delivery identity and malformed or uncertain custody', async () => {
		const responses = [
			receipt('accepted', '22345678-1234-4234-8234-123456789abc'),
			new Response('{"custody":"maybe"}', { status: 202, headers: { 'content-type': 'application/json' } }),
			new Response(JSON.stringify({ custody: 'durable', delivery_id: DELIVERY, disposition: 'accepted' }), {
				status: 503,
				headers: { 'content-type': 'application/json' },
			}),
			new Response('x'.repeat(513), { status: 202, headers: { 'content-type': 'application/json' } }),
		]
		for (const response of responses) {
			await expect(
				forwardToApplication(event, new AbortController().signal, async () => response),
			).rejects.toThrow('application custody is uncertain')
		}
	})

	test('throws safely on timeout, cancellation, transport failure, and unavailable application', async () => {
		const waitForAbort = (_input: string | URL | Request, init?: RequestInit) =>
			new Promise<Response>((_resolve, reject) => {
				init?.signal?.addEventListener('abort', () => reject(init.signal?.reason), { once: true })
			})
		await expect(forwardToApplication(event, new AbortController().signal, waitForAbort, 5)).rejects.toThrow(
			'application custody is uncertain',
		)
		const cancelled = new AbortController()
		cancelled.abort()
		await expect(forwardToApplication(event, cancelled.signal, waitForAbort)).rejects.toThrow(
			'application custody is uncertain',
		)
		await expect(
			forwardToApplication(event, new AbortController().signal, async () => {
				throw new Error('transport included sensitive payload')
			}),
		).rejects.toThrow('application custody is uncertain')
	})

	test('bounds stalled bodies and cancels unconsumed invalid responses', async () => {
		let cancellations = 0
		const stalled = () =>
			new Response(
				new ReadableStream({
					pull: () => new Promise(() => {}),
					cancel: () => {
						cancellations += 1
						return new Promise(() => {})
					},
				}),
				{ status: 202, headers: { 'content-type': 'application/json' } },
			)
		await expect(
			forwardToApplication(event, new AbortController().signal, async () => stalled(), 5),
		).rejects.toThrow('application custody is uncertain')
		const body = () =>
			new ReadableStream({
				cancel: () => {
					cancellations += 1
					return new Promise(() => {})
				},
			})
		await expect(
			forwardToApplication(
				event,
				new AbortController().signal,
				async () => new Response(body(), { status: 503, headers: { 'content-type': 'application/json' } }),
			),
		).rejects.toThrow('application custody is uncertain')
		expect(cancellations).toBe(2)
	})

	test('errors and registration produce no sensitive output canaries', async () => {
		privateRelayPath()
		const logs: unknown[][] = []
		let registration: { handler: (event: never, context: never) => Promise<void> } | undefined
		await plugin({
			logger: { log: (...values: unknown[]) => logs.push(values) },
			createWebhook: async (options: unknown) => {
				registration = options as typeof registration
				return { url: 'https://sensitive-capability.example' }
			},
		} as never)
		await expect(
			registration!.handler(event as never, { signal: new AbortController().signal } as never),
		).rejects.toThrow('application custody is uncertain')
		const rendered = JSON.stringify(logs)
		expect(rendered).toBe('[]')
		expect(rendered).not.toContain('sensitive-capability')
		expect(rendered).not.toContain('sensitive-signature')
		expect(rendered).not.toContain(DELIVERY)
	})
})
