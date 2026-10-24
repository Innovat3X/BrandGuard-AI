
"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { registerUser } from "@/services/auth.service";
import { ApiError } from "@/lib/api-client";

const registrationSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required."),
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Password is required.").max(1024),
  organization_name: z
    .string()
    .trim()
    .min(1, "Organisation name is required."),
});

type RegistrationValues = z.infer<typeof registrationSchema>;

export default function RegisterPage() {
  const [notice, setNotice] = useState("");
  const [apiError, setApiError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RegistrationValues>({
    resolver: zodResolver(registrationSchema),
    defaultValues: {
      full_name: "",
      email: "",
      password: "",
      organization_name: "",
    },
  });

  async function onSubmit(values: RegistrationValues) {
    setNotice("");
    setApiError("");
    setIsSubmitting(true);

    try {
      const response = await registerUser(values);

      setNotice(
        `Account created successfully for ${response.organization.name}. The backend returned your registration details.`
      );

      reset();
    } catch (error) {
      if (error instanceof ApiError) {
        setApiError(error.message);
      } else {
        setApiError(
          "Unable to complete registration. Please try again."
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f7fb] px-5 py-12">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
        <Link href="/" className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-600 text-xl font-bold text-white">
            B
          </span>
          <span className="text-xl font-bold text-slate-900">
            BrandGuard <span className="text-violet-600">AI</span>
          </span>
        </Link>

        <div className="mt-8">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Create your account
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Set up your account and organisation to get started.
          </p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="mt-7 space-y-4"
        >
          <div>
            <label htmlFor="full_name" className="mb-2 block text-sm font-medium text-slate-700">
              Full name
            </label>
            <input
              id="full_name"
              autoComplete="name"
              placeholder="Your full name"
              aria-invalid={Boolean(errors.full_name)}
              {...register("full_name")}
              className="w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            />
            {errors.full_name && (
              <p role="alert" className="mt-1 text-xs text-red-600">
                {errors.full_name.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-700">
              Email address
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              aria-invalid={Boolean(errors.email)}
              {...register("email")}
              className="w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            />
            {errors.email && (
              <p role="alert" className="mt-1 text-xs text-red-600">
                {errors.email.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="Create a password"
              aria-invalid={Boolean(errors.password)}
              {...register("password")}
              className="w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            />
            {errors.password && (
              <p role="alert" className="mt-1 text-xs text-red-600">
                {errors.password.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="organization_name"
              className="mb-2 block text-sm font-medium text-slate-700"
            >
              Organisation name
            </label>
            <input
              id="organization_name"
              placeholder="Your organisation"
              aria-invalid={Boolean(errors.organization_name)}
              {...register("organization_name")}
              className="w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            />
            {errors.organization_name && (
              <p role="alert" className="mt-1 text-xs text-red-600">
                {errors.organization_name.message}
              </p>
            )}
          </div>

          {apiError && (
            <p
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              {apiError}
            </p>
          )}

          {notice && (
            <p
              role="status"
              className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
            >
              {notice}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
          >
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-7 text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-semibold text-violet-700 hover:text-violet-900"
          >
            Sign in
          </Link>
        </p>

        <p className="mt-8 border-t border-slate-100 pt-5 text-center text-xs text-slate-400">
          BrandGuard AI · Brand Governance Platform
        </p>
      </section>
    </main>
  );
}
