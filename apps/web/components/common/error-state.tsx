import { CircleAlertIcon, LockIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api/client";

export function ErrorState({
  error,
  title,
  onRetry,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}) {
  const forbidden = isApiError(error, 403);
  const message = error instanceof Error ? error.message : "Something went wrong.";
  const Icon = forbidden ? LockIcon : CircleAlertIcon;
  return (
    <Alert variant={forbidden ? "default" : "destructive"}>
      <Icon />
      <AlertTitle>{title ?? (forbidden ? "No access" : "Couldn't load this")}</AlertTitle>
      <AlertDescription>
        <p>{message}</p>
        {onRetry && !forbidden && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            Try again
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
