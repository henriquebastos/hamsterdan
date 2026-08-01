import type { PluginAPI, WebhookEvent } from '@ampcode/plugin'
import { chmodSync, closeSync, fsyncSync, mkdirSync, openSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

const APPLICATION_ENDPOINT = 'http://127.0.0.1:8000/github/webhooks'
const APPLICATION_TIMEOUT_MS = 5_000
const MAX_RECEIPT_BYTES = 512
const CUSTODY_UNCERTAIN = 'application custody is uncertain'
const RELAY_REGISTRATION_FILE = resolve(import.meta.dir, '..', 'runtime', 'github-webhook.json')
const FORWARDED_HEADERS = [
	'content-type',
	'x-hub-signature-256',
	'x-github-event',
	'x-github-delivery',
] as const

type RelayEvent = Pick<WebhookEvent, 'body' | 'headers'>
type Fetch = typeof fetch

function retainRegistration(url: string): void {
	const path = process.env.HAMSTERDAN_RELAY_FILE || RELAY_REGISTRATION_FILE
	const directory = dirname(path)
	mkdirSync(directory, { recursive: true, mode: 0o700 })
	chmodSync(directory, 0o700)
	const temporary = join(directory, `.github-webhook-${process.pid}-${crypto.randomUUID()}.tmp`)
	const descriptor = openSync(temporary, 'wx', 0o600)
	try {
		writeFileSync(descriptor, JSON.stringify({ key: 'hamsterdan-github', url }) + '\n')
		fsyncSync(descriptor)
	} finally {
		closeSync(descriptor)
	}
	renameSync(temporary, path)
	const directoryDescriptor = openSync(directory, 'r')
	try {
		fsyncSync(directoryDescriptor)
	} finally {
		closeSync(directoryDescriptor)
	}
}

function cancelBody(response: Response): void {
	void response.body?.cancel().catch(() => {})
}

async function boundedBody(response: Response, signal: AbortSignal): Promise<Uint8Array> {
	const declared = response.headers.get('content-length')
	if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > MAX_RECEIPT_BYTES)) {
		cancelBody(response)
		throw new Error(CUSTODY_UNCERTAIN)
	}
	if (response.body === null) return new Uint8Array()
	const reader = response.body.getReader()
	const chunks: Uint8Array[] = []
	let size = 0
	let complete = false
	let rejectAbort: (reason: unknown) => void = () => {}
	const aborted = new Promise<never>((_resolve, reject) => {
		rejectAbort = reject
	})
	const abort = () => {
		void reader.cancel().catch(() => {})
		rejectAbort(signal.reason)
	}
	signal.addEventListener('abort', abort, { once: true })
	try {
		signal.throwIfAborted()
		while (true) {
			const { done, value } = await Promise.race([reader.read(), aborted])
			if (done) {
				complete = true
				break
			}
			size += value.byteLength
			if (size > MAX_RECEIPT_BYTES) throw new Error(CUSTODY_UNCERTAIN)
			chunks.push(value)
		}
		signal.throwIfAborted()
	} finally {
		signal.removeEventListener('abort', abort)
		if (complete) reader.releaseLock()
		else void reader.cancel().catch(() => {})
	}
	const body = new Uint8Array(size)
	let offset = 0
	for (const chunk of chunks) {
		body.set(chunk, offset)
		offset += chunk.byteLength
	}
	return body
}

export async function forwardToApplication(
	event: RelayEvent,
	handlerSignal: AbortSignal,
	fetcher: Fetch = fetch,
	timeoutMs = APPLICATION_TIMEOUT_MS,
): Promise<void> {
	try {
		handlerSignal.throwIfAborted()
		const headers = Object.fromEntries(FORWARDED_HEADERS.map((name) => [name, event.headers[name]]))
		if (Object.values(headers).some((value) => typeof value !== 'string')) throw new Error(CUSTODY_UNCERTAIN)
		const signal = AbortSignal.any([handlerSignal, AbortSignal.timeout(timeoutMs)])
		const response = await fetcher(APPLICATION_ENDPOINT, {
			method: 'POST',
			headers: headers as Record<string, string>,
			body: event.body,
			signal,
		})
		const contentType = response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase()
		if (response.status !== 202 || contentType !== 'application/json') {
			cancelBody(response)
			throw new Error(CUSTODY_UNCERTAIN)
		}
		const receipt = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await boundedBody(response, signal)))
		signal.throwIfAborted()
		const keys = Object.keys(receipt).sort()
		if (
			keys.length !== 3 ||
			keys[0] !== 'custody' ||
			keys[1] !== 'delivery_id' ||
			keys[2] !== 'disposition' ||
			receipt.custody !== 'durable' ||
			receipt.delivery_id !== event.headers['x-github-delivery'] ||
			!['accepted', 'accepted_terminal', 'duplicate'].includes(receipt.disposition)
		) {
			throw new Error(CUSTODY_UNCERTAIN)
		}
	} catch {
		throw new Error(CUSTODY_UNCERTAIN)
	}
}

export default async function (amp: PluginAPI): Promise<void> {
	const registration = await amp.createWebhook({
		key: 'hamsterdan-github',
		headers: FORWARDED_HEADERS,
		handler: (event, context) => forwardToApplication(event, context.signal),
	})
	retainRegistration(registration.url)
}
