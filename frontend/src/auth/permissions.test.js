import test from "node:test";
import assert from "node:assert/strict";

import { PROTECTED_ROUTE_ROLES, canAccessPath, landingPathForRole, rolesForPath } from "./permissions.js";

const PROTECTED_APP_ROUTES = [
  "/sinh-cau-hoi",
  "/quan-ly",
  "/lam-de-thi",
  "/lam-de-thi/:examId",
  "/kiem-duyet",
  "/tong-quan",
  "/danh-muc",
  "/quan-ly-nguoi-dung",
  "/nhat-ky-he-thong",
  "/quan-ly-job",
  "/quan-ly-moodle",
  "/lich-cong-viec",
  "/ho-so",
];

test("admin can access business superuser routes", () => {
  assert.equal(canAccessPath("Admin", "/sinh-cau-hoi"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly"), true);
  assert.equal(canAccessPath("Admin", "/lam-de-thi/abc123"), true);
  assert.equal(canAccessPath("Admin", "/kiem-duyet"), true);
  assert.equal(canAccessPath("Admin", "/tong-quan"), true);
  assert.equal(canAccessPath("Admin", "/nhat-ky-he-thong"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly-job"), true);
  assert.equal(canAccessPath("Admin", "/quan-ly-moodle"), true);
});

test("teacher cannot access reviewer or admin-only routes", () => {
  assert.equal(canAccessPath("Teacher", "/kiem-duyet"), false);
  assert.equal(canAccessPath("Teacher", "/tong-quan"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-nguoi-dung"), false);
  assert.equal(canAccessPath("Teacher", "/nhat-ky-he-thong"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-job"), false);
  assert.equal(canAccessPath("Teacher", "/quan-ly-moodle"), false);
});

test("direct URL permission and landing path use the same route map", () => {
  assert.deepEqual(rolesForPath("/lam-de-thi/abc123"), ["Teacher", "Admin"]);
  assert.equal(landingPathForRole("Admin"), "/tong-quan");
  assert.equal(landingPathForRole("Admin", "/kiem-duyet?status=PENDING"), "/kiem-duyet?status=PENDING");
  assert.equal(landingPathForRole("Teacher", "/kiem-duyet"), "/sinh-cau-hoi");
});

test("protected app routes are declared in the central permission map", () => {
  assert.deepEqual(Object.keys(PROTECTED_ROUTE_ROLES), PROTECTED_APP_ROUTES);
});
