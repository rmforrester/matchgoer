// Only public browser configuration belongs in the bundled application.
export function buildDefines(env = process.env) {
  const mode = env.MATCHGOER_NATIVE_TARGET;
  if (!["synthetic", "beta"].includes(mode)) throw new Error("Set MATCHGOER_NATIVE_TARGET to synthetic or beta explicitly");
  const values = mode === "synthetic" ? {
    NEXT_PUBLIC_API_BASE_URL: "https://api.example.test",
    NEXT_PUBLIC_SUPABASE_URL: "https://auth.example.test",
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "synthetic-test-key",
    NEXT_PUBLIC_GEOAPIFY_API_KEY: "synthetic-geoapify-key",
  } : Object.fromEntries([
    "NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "NEXT_PUBLIC_GEOAPIFY_API_KEY",
  ].map(name => {
    const value = env[name]?.trim();
    if (!value || /example\.test|synthetic/i.test(value)) throw new Error(`Missing or invalid public native configuration: ${name}`);
    return [name, value];
  }));
  if (mode === "beta") {
    for (const [name, expected] of Object.entries({
      NEXT_PUBLIC_API_BASE_URL: "https://api.beta.matchgoer.com",
      NEXT_PUBLIC_SUPABASE_URL: "https://xqnjayincslrlyfuvdys.supabase.co",
    })) {
      if (values[name].replace(/\/$/, "") !== expected) throw new Error(`Unexpected native service origin: ${name}`);
    }
    const key = values.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!key.startsWith("sb_publishable_")) {
      let role;
      try { role = JSON.parse(Buffer.from(key.split(".")[1], "base64url").toString()).role; } catch {}
      if (role !== "anon") throw new Error("Only a public Supabase publishable/anon key may enter the app");
    }
  }
  // Native Google return handling is not yet implemented; analytics stays off.
  Object.assign(values, {NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED: "false", NEXT_PUBLIC_GA_MEASUREMENT_ID: ""});
  return {"process.env": "{}", "process.env.NODE_ENV": JSON.stringify("production"),
    ...Object.fromEntries(Object.entries(values).map(([key,value]) => [`process.env.${key}`, JSON.stringify(value)]))};
}
