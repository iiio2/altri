"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ErrorState } from "@/components/common/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { meQuery } from "@/lib/api/queries";

/** Home: open the signed-in user's first team. */
export default function Home() {
  const router = useRouter();
  const me = useQuery(meQuery);
  const firstTeam = me.data?.teams[0];

  useEffect(() => {
    if (firstTeam) router.replace(`/teams/${firstTeam.id}`);
  }, [firstTeam, router]);

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-4 py-12">
      {me.isError ? (
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      ) : me.data && !firstTeam ? (
        <p className="text-sm text-muted-foreground">You aren&apos;t on any team yet.</p>
      ) : (
        <Skeleton className="h-24" aria-label="Loading" />
      )}
    </main>
  );
}
