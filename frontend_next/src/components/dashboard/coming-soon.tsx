import { Card, CardContent } from "@/components/ui/card";

export function ComingSoon({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <div className="text-4xl">🚧</div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="max-w-md text-sm text-muted-foreground">{body}</p>
        </CardContent>
      </Card>
    </div>
  );
}
