"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { useRouter } from "next/navigation";

import { ErrorState } from "@/components/common/error-state";
import { UserAvatar } from "@/components/common/user-avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap } from "@/lib/api/client";
import { usersQuery } from "@/lib/api/queries";
import { roleLabel } from "@/lib/format";

export function UserSwitcher() {
  const router = useRouter();
  const qc = useQueryClient();
  const users = useQuery(usersQuery);

  const login = useMutation({
    mutationFn: (email: string) => unwrap(api.POST("/api/v1/auth/login", { body: { email } })),
    onSuccess: (me) => {
      // A different user sees different teams and permissions: drop everything cached for the previous one.
      qc.clear();
      const first = me.teams[0];
      router.replace(first ? `/teams/${first.id}` : "/");
    },
  });

  if (users.isPending) {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="Loading users">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    );
  }
  if (users.isError) return <ErrorState error={users.error} onRetry={() => users.refetch()} />;

  return (
    <div className="space-y-3">
      {login.isError && <ErrorState error={login.error} />}
      <ul className="divide-y rounded-lg border">
        {users.data.map((user) => {
          const pending = login.isPending && login.variables === user.email;
          return (
            <li key={user.id}>
              <button
                type="button"
                disabled={login.isPending}
                onClick={() => login.mutate(user.email)}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left outline-none hover:bg-muted/60 focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
              >
                <UserAvatar name={user.name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{user.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
                </span>
                {pending ? (
                  <Loader2Icon className="size-4 animate-spin text-muted-foreground" aria-label="Signing in" />
                ) : (
                  <Badge variant={user.role === "observer" ? "outline" : "secondary"}>{roleLabel[user.role]}</Badge>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
