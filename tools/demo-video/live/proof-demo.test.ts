import {expect, test} from "bun:test";
import {validateShot, verifyDigest, type Shot} from "./proof-demo";
import {sha256} from "./render";

const shot: Shot = {id: "finding", source: "12-findings.after.html", yFrom: 1100, yTo: 1100, seconds: 14, caption: "A finding attached to the changed lines."};

test("evidence crops stay inside the source at both ends of a pan", () => {
  expect(() => validateShot(shot, 1280, 2805)).not.toThrow();
  expect(() => validateShot({...shot, yTo: 2300}, 1280, 2805)).toThrow("beyond its evidence");
  expect(() => validateShot(shot, 640, 2805)).toThrow("beyond its evidence");
});

test("captions leave reading time before the next transition", () => {
  expect(() => validateShot({...shot, seconds: 4, caption: "The reviewer asks the author to fix every finding before approving the repaired pull request."}, 1280, 2805)).toThrow("reading time");
});

test("edited screenshots cannot enter a video under an earlier evidence hash", () => {
  const bytes = Buffer.from("accepted screenshot");
  expect(() => verifyDigest(bytes, sha256(bytes), "still")).not.toThrow();
  expect(() => verifyDigest(Buffer.from("changed screenshot"), sha256(bytes), "still")).toThrow("recorded hash");
});
