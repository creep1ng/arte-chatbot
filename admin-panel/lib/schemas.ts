import { z } from "zod";

const optionalString = z.preprocess(
  (value) => (value === "" || value === null ? undefined : value),
  z.string().optional(),
);

const optionalNumber = (schema: z.ZodNumber) =>
  z.preprocess(
    (value) => {
      if (value === "" || value === null || Number.isNaN(value)) {
        return undefined;
      }
      return value;
    },
    schema.optional(),
  );

const optionalBoolean = z.preprocess(
  (value) => (value === null ? undefined : value),
  z.boolean().optional(),
);

export const ProductVariantSchema = z.object({
  modelo: z.string().min(1),
  parametros_clave: z.record(z.string(), z.unknown()).default({}),
});

export const CatalogProductSchema = z.object({
  nombre_comercial: z.string().min(1).max(200),
  fabricante: z.string().min(1).max(100),
  categoria: z.string().min(1).max(50),
  subcategoria: z.string().max(50).optional(),
  descripcion: z.string().max(2000).optional(),
  ruta_s3: z
    .string()
    .regex(/^[a-zA-Z0-9_\-/]+\.[a-zA-Z0-9]+$/, "Ruta S3 inválida"),
  variantes: z.array(ProductVariantSchema).default([]),
  parametros_comunes: z.record(z.string(), z.unknown()).default({}),
});

export const MutableSettingsSchema = z
  .object({
    llm_model: optionalString,
    log_level: optionalString,
    escalation_confidence_threshold: optionalNumber(z.number().min(0).max(1)),
    false_positive_limit: optionalNumber(z.number().min(0).max(1)),
    false_negative_limit: optionalNumber(z.number().min(0).max(1)),
    whatsapp_formatter_enabled: optionalBoolean,
    split_messages_enabled: optionalBoolean,
    msg_delay_min_ms: optionalNumber(z.number().int().min(1000).max(10000)),
    msg_delay_max_ms: optionalNumber(z.number().int().min(1000).max(15000)),
    greeting_enabled: optionalBoolean,
    greeting_timezone: optionalString,
    multi_message_buffer_enabled: optionalBoolean,
    buffer_window_seconds: optionalNumber(z.number().int().min(1).max(15)),
    conversation_logging_enabled: optionalBoolean,
    conversation_log_prefix: optionalString,
    admin_api_key: optionalString,
  })
  .refine(
    (data) => {
      if (
        data.msg_delay_min_ms === undefined ||
        data.msg_delay_max_ms === undefined
      ) {
        return true;
      }
      return data.msg_delay_min_ms <= data.msg_delay_max_ms;
    },
    {
      message: "El retraso mínimo debe ser menor o igual al máximo",
      path: ["msg_delay_max_ms"],
    },
  );

export type MutableSettingsInput = z.infer<typeof MutableSettingsSchema>;
export type CatalogProductInput = z.infer<typeof CatalogProductSchema>;
