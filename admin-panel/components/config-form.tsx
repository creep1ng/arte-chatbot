"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm, type Resolver } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { extractFastApiFieldErrors, useUpdateConfig } from "@/lib/api";
import { MutableSettingsSchema, type MutableSettingsInput } from "@/lib/schemas";
import type { CurrentSettingsSnapshot, MutableSettings } from "@/lib/types";

interface ConfigFormProps {
  config: CurrentSettingsSnapshot;
}

const editableNumberFields: Array<{
  name: keyof MutableSettingsInput;
  label: string;
  min?: number;
  max?: number;
  step?: number;
}> = [
  {
    name: "escalation_confidence_threshold",
    label: "Umbral de confianza para escalamiento",
    min: 0,
    max: 1,
    step: 0.01,
  },
  { name: "false_positive_limit", label: "Límite falso positivo", min: 0, max: 1, step: 0.01 },
  { name: "false_negative_limit", label: "Límite falso negativo", min: 0, max: 1, step: 0.01 },
  { name: "msg_delay_min_ms", label: "Retraso mínimo de mensaje (ms)", min: 1000, max: 10000, step: 100 },
  { name: "msg_delay_max_ms", label: "Retraso máximo de mensaje (ms)", min: 1000, max: 15000, step: 100 },
  { name: "buffer_window_seconds", label: "Ventana de buffer (segundos)", min: 1, max: 15, step: 1 },
];

const editableTextFields: Array<{
  name: keyof MutableSettingsInput;
  label: string;
  type?: string;
}> = [
  { name: "llm_model", label: "Modelo LLM" },
  { name: "log_level", label: "Nivel de logs" },
  { name: "greeting_timezone", label: "Zona horaria de saludo" },
  { name: "conversation_log_prefix", label: "Prefijo de logs de conversación" },
  { name: "admin_api_key", label: "API key administrativa", type: "password" },
];

const editableBooleanFields: Array<{
  name: keyof MutableSettingsInput;
  label: string;
}> = [
  { name: "whatsapp_formatter_enabled", label: "Formato WhatsApp habilitado" },
  { name: "split_messages_enabled", label: "Dividir mensajes habilitado" },
  { name: "greeting_enabled", label: "Saludo habilitado" },
  { name: "multi_message_buffer_enabled", label: "Buffer multi-mensaje habilitado" },
  { name: "conversation_logging_enabled", label: "Logging de conversaciones habilitado" },
];

function normalizeMutable(settings: MutableSettings): MutableSettingsInput {
  return Object.fromEntries(
    Object.entries(settings).map(([key, value]) => [
      key,
      value === null ? undefined : value,
    ]),
  ) as MutableSettingsInput;
}

function cleanMutablePayload(values: MutableSettingsInput): MutableSettings {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined),
  ) as MutableSettings;
}

export function ConfigForm({ config }: ConfigFormProps) {
  const updateConfig = useUpdateConfig();
  const form = useForm<MutableSettingsInput>({
    resolver: zodResolver(MutableSettingsSchema) as Resolver<MutableSettingsInput>,
    defaultValues: normalizeMutable(config.mutable),
  });

  useEffect(() => {
    form.reset(normalizeMutable(config.mutable));
  }, [config.mutable, form]);

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await updateConfig.mutateAsync(cleanMutablePayload(values));
    } catch (error) {
      extractFastApiFieldErrors(error).forEach((fieldError) => {
        const fieldName = fieldError.loc.at(-1);
        if (typeof fieldName === "string") {
          form.setError(fieldName as keyof MutableSettingsInput, {
            type: "server",
            message: fieldError.msg,
          });
        }
      });
    }
  });

  return (
    <form className="space-y-8" onSubmit={onSubmit}>
      <section className="rounded-[1.5rem] border bg-card/95 p-6 shadow-sm">
        <h2 className="font-display text-2xl font-black text-primary">
          Configuración mutable
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Estos valores se envían al endpoint PUT /admin/config y se recargan en
          caliente en el backend.
        </p>

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {editableTextFields.map((field) => (
            <label className="space-y-2 text-sm font-semibold" key={field.name}>
              {field.label}
              <Input type={field.type ?? "text"} {...form.register(field.name)} />
              {form.formState.errors[field.name]?.message ? (
                <span className="text-xs text-destructive">
                  {form.formState.errors[field.name]?.message}
                </span>
              ) : null}
            </label>
          ))}

          {editableNumberFields.map((field) => (
            <label className="space-y-2 text-sm font-semibold" key={field.name}>
              {field.label}
              <Input
                type="number"
                min={field.min}
                max={field.max}
                step={field.step}
                {...form.register(field.name, {
                  setValueAs: (value) =>
                    value === "" ? undefined : Number(value),
                })}
              />
              {form.formState.errors[field.name]?.message ? (
                <span className="text-xs text-destructive">
                  {form.formState.errors[field.name]?.message}
                </span>
              ) : null}
            </label>
          ))}
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {editableBooleanFields.map((field) => (
            <label
              className="flex items-center gap-3 rounded-xl border bg-background/60 p-3 text-sm font-semibold"
              key={field.name}
            >
              <input
                className="h-4 w-4 accent-primary"
                type="checkbox"
                {...form.register(field.name)}
              />
              {field.label}
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-[1.5rem] border bg-card/95 p-6 shadow-sm">
        <h2 className="font-display text-2xl font-black text-primary">
          Configuración inmutable
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Estos valores requieren reinicio o gestión externa de secretos.
        </p>
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {Object.entries(config.immutable).map(([key, value]) => (
            <label className="space-y-2 text-sm font-semibold" key={key}>
              {key}
              <Input disabled readOnly value={value ?? ""} />
            </label>
          ))}
        </div>
      </section>

      <div className="flex justify-end">
        <Button disabled={updateConfig.isPending} type="submit">
          {updateConfig.isPending ? "Guardando…" : "Guardar configuración"}
        </Button>
      </div>
    </form>
  );
}
