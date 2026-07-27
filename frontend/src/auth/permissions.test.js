import test from "node:test";
import assert from "node:assert/strict";

import { canAccessPath, landingPathForRole, rolesForPath } from "./permissions.js";

test("admin can access business superuser routes", () => {
  assert.equal(canAccessPath("Admin", "/sinh-cau-hoi"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly"), true);
  assert.equal(canAccessPath("Admin", "/lam-de-thi/abc123"), true);
  assert.equal(canAccessPath("Admin", "/kiem-duyet"), true);
  assert.equal(canAccessPath("Admin", "/nhat-ky-he-thong"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly-job"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly-moodle"), true);
});

test("teacher cannot access reviewer or admin-only routes", () => {
  assert.equal(canAccessPath("Teacher", "/kiem-duyet"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-nguoi-dung"), false);
  assert.equal(canAccessPath("Teacher", "/nhat-ky-he-thong"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-job"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-moodle"), false);
});

test("direct URL permission and landing path use the same route map", () => {
  assert.deepEqual(rolesForPath("/lam-de-thi/abc123"), ["Teacher", "Admin"]);
  assert.equal(landingPathForRole("Admin", "/kiem-duyet?status=PENDING"), "/kiem-duyet?status=PENDING");
  assert.equal(landingPathForRole("Teacher", "/kiem-duyet"), "/sinh-cau-hoi");
});
