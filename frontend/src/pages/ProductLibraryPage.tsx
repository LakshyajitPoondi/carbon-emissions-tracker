import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { Product, ProductCreateRequest } from "../types";
import { hasOrganizationWriteAccess } from "../utils/organizationRoles";

interface ProductFormState {
  name: string;
  barcode: string;
  composition: string;
  emissionsValue: string;
  emissionsUnit: string;
  emissionsDescription: string;
  sourceReference: string;
}

const EMPTY_FORM: ProductFormState = {
  name: "",
  barcode: "",
  composition: "",
  emissionsValue: "",
  emissionsUnit: "kg CO2e/item",
  emissionsDescription: "",
  sourceReference: "",
};

function ProductBarcodeCell({ product }: { product: Product }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!product.barcode) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void apiClient
      .getProductBarcodeImage(product.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch(() => {
        // Legacy or arbitrary non-EAN Product barcodes legitimately have no
        // generated PNG. The text value remains useful and visible.
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [product.barcode, product.id]);

  if (!product.barcode) return <>Not assigned</>;

  return (
    <div className="product-barcode">
      <code>{product.barcode}</code>
      {imageUrl && (
        <>
          <img
            className="product-barcode__image"
            src={imageUrl}
            alt={`EAN-13 barcode for ${product.name}`}
          />
          <div className="product-barcode__actions">
            <a href={imageUrl} download={`product-${product.id}-barcode.png`}>
              Download PNG
            </a>
            <a href={imageUrl} target="_blank" rel="noreferrer">
              Open / print
            </a>
          </div>
        </>
      )}
    </div>
  );
}

export function ProductLibraryPage() {
  const { organization } = useAppState();

  if (!organization) {
    return (
      <main className="page">
        <h1>Product Library</h1>
        <p className="empty-state">
          Select an organization on the <Link to="/">Setup</Link> screen first.
        </p>
      </main>
    );
  }

  return (
    <ProductLibraryForOrganization
      key={organization.id}
      organizationId={organization.id}
      organizationName={organization.name}
      canManage={hasOrganizationWriteAccess(organization.role)}
    />
  );
}

function ProductLibraryForOrganization({
  organizationId,
  organizationName,
  canManage,
}: {
  organizationId: number;
  organizationName: string;
  canManage: boolean;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [listError, setListError] = useState<unknown>(null);
  const [form, setForm] = useState<ProductFormState>(EMPTY_FORM);
  const [editing, setEditing] = useState<Product | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<unknown>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setListError(null);
    try {
      setProducts(await apiClient.listProducts(organizationId));
      setStatus("ready");
    } catch (error) {
      setListError(error);
      setStatus("error");
    }
  }, [organizationId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const nextProducts = await apiClient.listProducts(organizationId);
        if (cancelled) return;
        setProducts(nextProducts);
        setStatus("ready");
      } catch (error) {
        if (cancelled) return;
        setListError(error);
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  function setField<K extends keyof ProductFormState>(
    field: K,
    value: ProductFormState[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function resetForm() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  }

  function beginEdit(product: Product) {
    setEditing(product);
    setForm({
      name: product.name,
      barcode: product.barcode ?? "",
      composition: product.composition,
      emissionsValue: product.emissions_value,
      emissionsUnit: product.emissions_unit,
      emissionsDescription: product.emissions_description,
      sourceReference: product.source_reference,
    });
    setFormError(null);
    setFeedback(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    setFeedback(null);

    const fields = {
      name: form.name,
      barcode: form.barcode.trim() || null,
      composition: form.composition,
      emissions_value: form.emissionsValue,
      emissions_unit: form.emissionsUnit,
      emissions_description: form.emissionsDescription,
      source_reference: form.sourceReference,
    };

    try {
      if (editing) {
        await apiClient.updateProduct(editing.id, fields);
        setFeedback(`Updated ${form.name.trim()}.`);
      } else {
        const request: ProductCreateRequest = {
          organization_id: organizationId,
          ...fields,
        };
        await apiClient.createProduct(request);
        setFeedback(`Added ${form.name.trim()} to the library.`);
      }
      resetForm();
      await load();
    } catch (error) {
      setFormError(error);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(product: Product) {
    if (!window.confirm(`Delete “${product.name}” from the Product Library?`)) return;
    setDeletingId(product.id);
    setDeleteError(null);
    setFeedback(null);
    try {
      await apiClient.deleteProduct(product.id);
      if (editing?.id === product.id) resetForm();
      setFeedback(`Deleted ${product.name}.`);
      await load();
    } catch (error) {
      setDeleteError(error);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="page">
      <h1>Product Library</h1>
      <p className="page__intro">
        Manually maintained product composition and embodied-emissions reference data for{" "}
        <strong>{organizationName}</strong>.
      </p>
      <p className="result-panel__meta">
        Product figures are reference data and do not feed consumption calculations.
      </p>

      {canManage ? (
        <section className="card">
          <h2>{editing ? `Edit ${editing.name}` : "Add a product"}</h2>
          <form className="card__col" onSubmit={handleSubmit}>
            <div className="card__row">
              <div className="field">
                <label htmlFor="product-name">Product name</label>
                <input
                  id="product-name"
                  value={form.name}
                  onChange={(event) => setField("name", event.target.value)}
                  required
                  placeholder="Recycled aluminium bottle"
                />
              </div>
              <div className="field">
                <label htmlFor="product-barcode">
                  Barcode (optional — generated if blank)
                </label>
                <input
                  id="product-barcode"
                  value={form.barcode}
                  onChange={(event) => setField("barcode", event.target.value)}
                  placeholder="8901234567890"
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="product-composition">Composition / materials</label>
              <textarea
                id="product-composition"
                value={form.composition}
                onChange={(event) => setField("composition", event.target.value)}
                required
                rows={3}
                placeholder="70% recycled aluminium, 30% primary aluminium"
              />
            </div>
            <div className="card__row">
              <div className="field">
                <label htmlFor="product-emissions-value">Emissions value</label>
                <input
                  id="product-emissions-value"
                  type="number"
                  min="0"
                  step="any"
                  value={form.emissionsValue}
                  onChange={(event) => setField("emissionsValue", event.target.value)}
                  required
                  placeholder="1.25"
                />
              </div>
              <div className="field">
                <label htmlFor="product-emissions-unit">Unit</label>
                <input
                  id="product-emissions-unit"
                  value={form.emissionsUnit}
                  onChange={(event) => setField("emissionsUnit", event.target.value)}
                  required
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="product-emissions-description">What the figure represents</label>
              <textarea
                id="product-emissions-description"
                value={form.emissionsDescription}
                onChange={(event) => setField("emissionsDescription", event.target.value)}
                required
                rows={2}
                placeholder="Cradle-to-gate embodied emissions per finished bottle"
              />
            </div>
            <div className="field">
              <label htmlFor="product-source-reference">Source / basis</label>
              <input
                id="product-source-reference"
                value={form.sourceReference}
                onChange={(event) => setField("sourceReference", event.target.value)}
                required
                placeholder="Supplier EPD, 2026"
              />
            </div>
            <div className="button-row">
              <button type="submit" disabled={saving}>
                {saving ? "Saving…" : editing ? "Save changes" : "Add product"}
              </button>
              {editing && (
                <button type="button" className="link-button" onClick={resetForm}>
                  Cancel edit
                </button>
              )}
            </div>
            {formError !== null && <ErrorBanner error={formError} />}
          </form>
        </section>
      ) : (
        <p className="empty-state">
          EMPLOYEE access can view products; OWNER or ADMIN is required to add, edit, or delete them.
        </p>
      )}

      {feedback && <p className="selection-confirm">{feedback}</p>}
      {deleteError !== null && <ErrorBanner error={deleteError} />}

      <section className="card">
        <h2>Products</h2>
        {status === "loading" && <LoadingState label="Loading products…" />}
        {status === "error" && <ErrorBanner error={listError} onRetry={load} />}
        {status === "ready" &&
          (products.length === 0 ? (
            <p className="empty-state">No products have been added yet.</p>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col">Barcode</th>
                    <th scope="col">Composition</th>
                    <th scope="col">Emissions</th>
                    <th scope="col">Description and source</th>
                    {canManage && <th scope="col">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id}>
                      <td><strong>{product.name}</strong></td>
                      <td><ProductBarcodeCell product={product} /></td>
                      <td>{product.composition}</td>
                      <td>{product.emissions_value} {product.emissions_unit}</td>
                      <td>
                        {product.emissions_description}
                        <br />
                        <span className="result-panel__meta">Source: {product.source_reference}</span>
                      </td>
                      {canManage && (
                        <td>
                          <div className="button-row">
                            <button type="button" onClick={() => beginEdit(product)}>Edit</button>
                            <button
                              type="button"
                              className="danger-button"
                              disabled={deletingId === product.id}
                              onClick={() => void handleDelete(product)}
                            >
                              {deletingId === product.id ? "Deleting…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </section>
    </main>
  );
}
