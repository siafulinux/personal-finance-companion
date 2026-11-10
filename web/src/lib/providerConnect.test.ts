import { describe, expect, it } from "vitest";
import { tellerFinishPayload, type TellerEnrollment } from "./providerConnect";

describe("tellerFinishPayload", () => {
  it("forwards the access token, the signed nonce and the enrolment identity", () => {
    const enrollment: TellerEnrollment = {
      accessToken: "token_live_abc",
      user: { id: "usr_1" },
      enrollment: { id: "enr_1", institution: { name: "USAA" } },
      signatures: ["sig-a", "sig-b"],
    };

    expect(tellerFinishPayload(enrollment, "nonce-123")).toEqual({
      public_token: "token_live_abc",
      nonce: "nonce-123",
      user_id: "usr_1",
      enrollment_id: "enr_1",
      signatures: ["sig-a", "sig-b"],
    });
  });

  it("tolerates an enrolment without a signature list", () => {
    const payload = tellerFinishPayload({ accessToken: "token_sandbox" }, "nonce-9");
    expect(payload.public_token).toBe("token_sandbox");
    expect(payload.signatures).toEqual([]);
    expect(payload.user_id).toBeNull();
    expect(payload.enrollment_id).toBeNull();
  });

  it("never invents a consent field or a provider name for the server", () => {
    const payload = tellerFinishPayload({ accessToken: "token" }, "nonce");
    expect(Object.keys(payload)).toEqual([
      "public_token",
      "nonce",
      "user_id",
      "enrollment_id",
      "signatures",
    ]);
  });
});
