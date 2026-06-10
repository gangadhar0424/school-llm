"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { User, Role } from "@/lib/types";
import { homeForRole } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

const SUBJECTS = ["Math", "Science", "English", "Social", "Computer"];
const CLASSES = Array.from({ length: 10 }, (_, i) => i + 1);
const SECTIONS = ["A", "B", "C"];
const ALL_CLASS_SECTIONS = CLASSES.flatMap((c) =>
  SECTIONS.map((s) => `${c}${s}`)
);

export function LoginClient({
  initialTab,
}: {
  initialTab: "login" | "signup";
}) {
  const [tab, setTab] = React.useState<"login" | "signup">(initialTab);

  return (
    <Card>
      <CardContent className="p-6">
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as "login" | "signup")}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="login">🔑 Login</TabsTrigger>
            <TabsTrigger value="signup">📝 Sign Up</TabsTrigger>
          </TabsList>
          <TabsContent value="login" className="pt-4">
            <LoginForm />
          </TabsContent>
          <TabsContent value="signup" className="pt-4">
            <SignupForm onCreated={() => setTab("login")} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

// ── Login form ───────────────────────────────────────────────────────────

function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState<Role>("student");
  const [showPassword, setShowPassword] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email || !password) {
      setError("Please fill in all fields.");
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, role }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.error || "Login failed.");
        return;
      }
      const user = body.user as User;
      toast.success(`Welcome, ${user.username || user.email}!`);
      router.push(homeForRole(user.role));
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Cannot reach the server. Is the backend running?"
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="text-base font-semibold">Welcome back</div>
      <Field id="login-email" label="Username or email">
        <Input
          id="login-email"
          // `type="text"` instead of "email" because the ERP accepts username,
          // email, OR phone in this same field. Browser email-format validation
          // would reject perfectly valid usernames.
          type="text"
          autoComplete="username"
          placeholder="username, email, or phone"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>
      <Field id="login-password" label="Password">
        <PasswordInput
          id="login-password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          show={showPassword}
          onToggle={() => setShowPassword((s) => !s)}
        />
      </Field>
      <Field id="login-role" label="I am a…">
        <Select value={role} onValueChange={(v) => setRole(v as Role)}>
          <SelectTrigger id="login-role">
            <SelectValue placeholder="Pick a role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="student">Student</SelectItem>
            <SelectItem value="teacher">Teacher</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Must match the role this account was created with.
        </p>
      </Field>

      {error && <ErrorBanner message={error} />}

      <Button type="submit" disabled={pending} className="mt-2">
        {pending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Verifying…
          </>
        ) : (
          "Login →"
        )}
      </Button>
    </form>
  );
}

// ── Signup form ──────────────────────────────────────────────────────────

function SignupForm({ onCreated }: { onCreated: () => void }) {
  const [role, setRole] = React.useState<Role>("student");
  const [email, setEmail] = React.useState("");
  const [username, setUsername] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);

  // Student-only
  const [classLevel, setClassLevel] = React.useState<string>("1");
  const [section, setSection] = React.useState<string>("A");

  // Teacher-only
  const [subjects, setSubjects] = React.useState<string[]>([]);
  const [assignedClasses, setAssignedClasses] = React.useState<string[]>([]);

  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !username || !password || !confirm) {
      setError("Please fill in all required fields.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (role === "teacher" && (subjects.length === 0 || assignedClasses.length === 0)) {
      setError(
        "Teachers must select at least one subject and one assigned class."
      );
      return;
    }

    setPending(true);
    try {
      const body: Record<string, unknown> = {
        email,
        username,
        password,
        full_name: fullName || "",
        role,
      };
      if (role === "student") {
        body.class_level = Number(classLevel);
        body.section = section;
      }
      if (role === "teacher") {
        body.subjects_taught = subjects;
        body.assigned_classes = assignedClasses;
      }
      const res = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || "Signup failed.");
        return;
      }
      toast.success("✅ Account created! Sign in to continue.");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <Field id="signup-role" label="Register as">
        <Select value={role} onValueChange={(v) => setRole(v as Role)}>
          <SelectTrigger id="signup-role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="student">Student</SelectItem>
            <SelectItem value="teacher">Teacher</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
          </SelectContent>
        </Select>
      </Field>

      <div className="text-base font-semibold">
        Create your account ({prettyRole(role)})
      </div>

      <Field id="su-email" label="Email">
        <Input
          id="su-email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>
      <Field id="su-username" label="Username">
        <Input
          id="su-username"
          autoComplete="username"
          placeholder="johndoe"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </Field>
      <Field id="su-fullname" label="Full Name">
        <Input
          id="su-fullname"
          placeholder="John Doe (optional)"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
      </Field>
      <Field id="su-pw" label="Password">
        <PasswordInput
          id="su-pw"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          show={showPw}
          onToggle={() => setShowPw((s) => !s)}
          placeholder="Min 8 characters"
        />
      </Field>
      <Field id="su-confirm" label="Confirm Password">
        <PasswordInput
          id="su-confirm"
          autoComplete="new-password"
          value={confirm}
          onChange={setConfirm}
          show={showConfirm}
          onToggle={() => setShowConfirm((s) => !s)}
          placeholder="Repeat password"
        />
      </Field>

      {role === "student" && (
        <div className="grid grid-cols-2 gap-3">
          <Field id="su-cls" label="Class">
            <Select value={classLevel} onValueChange={setClassLevel}>
              <SelectTrigger id="su-cls">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLASSES.map((c) => (
                  <SelectItem key={c} value={String(c)}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id="su-sec" label="Section">
            <Select value={section} onValueChange={setSection}>
              <SelectTrigger id="su-sec">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SECTIONS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <p className="col-span-2 text-xs text-muted-foreground">
            You will be registered to class{" "}
            <strong>
              {classLevel}
              {section}
            </strong>
            .
          </p>
        </div>
      )}

      {role === "teacher" && (
        <>
          <Field id="su-subs" label="Subjects you teach">
            <MultiChips
              options={SUBJECTS}
              selected={subjects}
              onChange={setSubjects}
            />
          </Field>
          <Field id="su-cls" label="Assigned classes (class + section)">
            <MultiChips
              options={ALL_CLASS_SECTIONS}
              selected={assignedClasses}
              onChange={setAssignedClasses}
              compact
            />
          </Field>
        </>
      )}

      <div className="rounded-md border-l-2 border-l-primary bg-primary-chip px-3 py-2 text-xs text-muted-foreground">
        ⚠️ The role you select here is permanent for this account.
      </div>

      {error && <ErrorBanner message={error} />}

      <Button type="submit" disabled={pending} className="mt-2">
        {pending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Creating…
          </>
        ) : (
          "Create Account →"
        )}
      </Button>
    </form>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function PasswordInput({
  id,
  value,
  onChange,
  show,
  onToggle,
  placeholder = "••••••••",
  autoComplete,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  show: boolean;
  onToggle: () => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pr-10"
        required
      />
      <button
        type="button"
        onClick={onToggle}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {message}
    </div>
  );
}

function MultiChips({
  options,
  selected,
  onChange,
  compact = false,
}: {
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  compact?: boolean;
}) {
  const toggle = (v: string) => {
    onChange(
      selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]
    );
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => {
        const isSel = selected.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={cn(
              "rounded-full border px-2.5 py-1 transition-colors",
              compact ? "text-xs" : "text-sm",
              isSel
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-surface text-foreground hover:bg-muted"
            )}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}

function prettyRole(r: Role): string {
  return r.charAt(0).toUpperCase() + r.slice(1);
}
