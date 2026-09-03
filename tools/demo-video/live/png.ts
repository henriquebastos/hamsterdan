export type PngDimensions = Readonly<{width: number; height: number}>;

const SIGNATURE = "89504e470d0a1a0a";

export const pngDimensions = (bytes: Uint8Array, label = "browser screenshot"): PngDimensions => {
  if (bytes.length < 24 || Buffer.from(bytes.subarray(0, 8)).toString("hex") !== SIGNATURE) {
    throw new Error(`${label} is not a PNG`);
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return {width: view.getUint32(16), height: view.getUint32(20)};
};
