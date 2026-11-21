"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, ChevronsUpDownIcon, LogOutIcon, UsersIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { UserAvatar } from "@/components/common/user-avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, unwrap } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";
import { roleLabel } from "@/lib/format";
import type { LiveStatus } from "@/lib/live/use-team-live";
import { cn } from "@/lib/utils";

export function AppHeader({
  teamId,
  teamName,
  me,
  live,
}: {
  teamId: string;
  teamName?: string;
  me?: Me;
  live: LiveStatus | null;
}) {
  return (
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-2 px-4">
        <Link href="/" className="mr-1 text-sm font-semibold tracking-tight">
          Altri
        </Link>
        <span className="text-muted-foreground/60" aria-hidden="true">
          /
        </span>
        {me && <TeamSwitcher teams={me.teams} currentId={teamId} currentName={teamName} />}
        <div className="ml-auto flex items-center gap-3">
          {live && <LiveIndicator status={live} />}
          {me && <UserMenu me={me} />}
        </div>
      </div>
    </header>
  );
}

function TeamSwitcher({ teams, currentId, currentName }: { teams: Me["teams"]; currentId: string; currentName?: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-1.5 px-2 font-medium" aria-label={`Team: ${currentName ?? currentId}. Switch team`}>
          {currentName ?? "Choose a team"}
          <ChevronsUpDownIcon className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Your teams</DropdownMenuLabel>
        {teams.map((team) => (
          <DropdownMenuItem key={team.id} asChild>
            <Link href={`/teams/${team.id}`} aria-current={team.id === currentId ? "page" : undefined}>
              <span className="flex-1">{team.name}</span>
              {team.id === currentId && <CheckIcon />}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const LIVE_LABEL: Record<LiveStatus, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
};

function LiveIndicator({ status }: { status: LiveStatus }) {
  return (
    <output className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="live-status" data-status={status}>
      <span
        aria-hidden="true"
        className={cn("size-2 rounded-full", status === "live" ? "bg-success" : "animate-pulse bg-warning")}
      />
      {LIVE_LABEL[status]}
    </output>
  );
}

function UserMenu({ me }: { me: Me }) {
  const router = useRouter();
  const qc = useQueryClient();
  const logout = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    onSettled: () => {
      qc.clear();
      router.replace("/login");
    },
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 px-1.5" aria-label={`Signed in as ${me.user.name}. Account menu`}>
          <UserAvatar name={me.user.name} className="size-7" />
          <span className="hidden text-sm font-medium sm:inline">{me.user.name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <span className="block text-sm font-medium text-foreground">{me.user.name}</span>
          <span className="block text-xs text-muted-foreground">
            {roleLabel[me.user.role]}
            {!me.can_write && " · read-only"}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/login">
            <UsersIcon />
            Switch user
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => logout.mutate()} disabled={logout.isPending}>
          <LogOutIcon />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
