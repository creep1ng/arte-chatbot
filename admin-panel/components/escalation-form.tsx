"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { extractFastApiFieldErrors, useUpdateConfig } from "@/lib/api";
import type { MutableSettingsInput } from "@/lib/schemas";
import type { CurrentSettingsSnapshot, MutableSettings } from "@/lib/types";

interface EscalationFormProps {
  config: CurrentSettingsSnapshot;
}

type EscalationSettingsInput = Pick<
  MutableSettingsInput,
  | "escalation_confidence_threshold"
  | "false_positive_limit"
  | "false_negative_limit"
>;

const optionalThreshold = z.preprocess(
  (value) => {
    if (value === "" || value === null || Number.isNaN(value)) {
      return undefined;
    }
    return value;
  },
  z.number().min(0).max(1).optional(),
);

const EscalationSettingsSchema = z.object({
  escalation_confidence_threshold: optionalThreshold,
  false_positive_limit: optionalThreshold,
  false_negative_limit: optionalThreshold,
});

function normalizeEscalation(
  settings: MutableSettings,
): EscalationSettingsInput {
  return {
    escalation_confidence_threshold:
      settings.escalation_confidence_threshold ?? undefined,
    false_positive_limit: settings.false_positive_limit ?? undefined,
    false_negative_limit: settings.false_negative_limit ?? undefined,
  };
}

export function EscalationForm({ config }: EscalationFormProps) {
  const [forcedKeywords, setForcedKeywords] = useState("");
  const updateConfig = useUpdateConfig();
  const form = useForm<EscalationSettingsInput>({
    resolver: zodResolver(EscalationSettingsSchema) as Resolver<EscalationSettingsInput>,
    defaultValues: normalizeEscalation(config.mutable),
  });
  const threshold = form.watch("escalation_confidence_threshold") ?? 0;

  useEffect(() => {
    form.reset(normalizeEscalation(config.mutable));
  }, [config.mutable, form]);

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await updateConfig.mutateAsync(values);
    } catch (error) {
      extractFastApiFieldErrors(error).forEach((fieldError) => {
        const fieldName = fieldError.loc.at(-1);
        if (typeof fieldName === "string") {
          form.setError(fieldName as keyof EscalationSettingsInput, {
            type: "server",
            message: fieldError.msg,
          });
        }
      });
    }
  });

  return (
    <form className="space-y-6" onSubmit={onSubmit}>
      <section className="rounded-[1.5rem] border bg-card/95 p-6 shadow-sm">
        <h2 className="font-display text-2xl font-black text-primary">
          Criterios de escalamiento
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Ajusta el umbral y los límites que determinan cuándo una conversación
          debe pasar a un agente humano.
        </p>

        <div className="mt-6 space-y-6">
          <label className="space-y-3 text-sm font-semibold">
            Umbral de confianza: {Number(threshold).toFixed(2)}
            <input
              aria-label="Umbral de confianza"
              className="w-full accent-primary"
              max={1}
              min={0}
              step={0.01}
              type="range"
              {...form.register("escalation_confidence_threshold", {
                setValueAs: (value) =>
                  value === "" ? undefined : Number(value),
              })}
            />
          </label>
          {form.formState.errors.escalation_confidence_threshold?.message ? (
            <p className="text-xs text-destructive">
              {form.formState.errors.escalation_confidence_threshold.message}
            </p>
          ) : null}

          <div className="grid gap-5 md:grid-cols-2">
            <label className="space-y-2 text-sm font-semibold">
              Límite falso positivo
              <Input
                max={1}
                min={0}
                step={0.01}
                type="number"
                {...form.register("false_positive_limit", {
                  setValueAs: (value) =>
                    value === "" ? undefined : Number(value),
                })}
              />
              {form.formState.errors.false_positive_limit?.message ? (
                <span className="text-xs text-destructive">
                  {form.formState.errors.false_positive_limit.message}
                </span>
              ) : null}
            </label>
            <label className="space-y-2 text-sm font-semibold">
              Límite falso negativo
              <Input
                max={1}
                min={0}
                step={0.01}
                type="number"
                {...form.register("false_negative_limit", {
                  setValueAs: (value) =>
                    value === "" ? undefined : Number(value),
                })}
              />
              {form.formState.errors.false_negative_limit?.message ? (
                <span className="text-xs text-destructive">
                  {form.formState.errors.false_negative_limit.message}
                </span>
              ) : null}
            </label>
          </div>
        </div>
      </section>

      <section className="rounded-[1.5rem] border border-dashed bg-card/80 p-6 shadow-sm">
        <h2 className="font-display text-xl font-black text-primary">
          Keywords forzosas
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          El backend de Slice 4 aún no expone un campo dedicado para keywords;
          este campo es local/no-op y documenta la necesidad para una iteración
          posterior sin inventar un endpoint nuevo.
        </p>
        <label className="mt-4 block space-y-2 text-sm font-semibold">
          Lista local de keywords
          <Input
            placeholder="garantía urgente, reclamo, asesor humano"
            value={forcedKeywords}
            onChange={(event) => setForcedKeywords(event.target.value)}
          />
        </label>
      </section>

      <div className="flex justify-end">
        <Button disabled={updateConfig.isPending} type="submit">
          {updateConfig.isPending ? "Guardando…" : "Guardar escalamiento"}
        </Button>
      </div>
    </form>
  );
}
