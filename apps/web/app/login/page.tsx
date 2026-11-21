import type { Metadata } from "next";

import { UserSwitcher } from "./user-switcher";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-4 py-12">
      <div className="space-y-1">
        <p className="text-sm font-semibold tracking-tight">Altri</p>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-muted-foreground">Choose a seeded user. Their role decides what they can change.</p>
      </div>
      <UserSwitcher />
    </main>
  );
}
