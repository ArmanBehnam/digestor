import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DeflectionItem {
  Description?: string;
  Combination?: string;
  LimitRatio?: string | null;
  Max?: string | null;
}

interface DeflectionCriteriaEditorProps {
  value: string;
  onSave: (newValue: string) => void;
  onCancel: () => void;
}

export const DeflectionCriteriaEditor = ({ value, onSave, onCancel }: DeflectionCriteriaEditorProps) => {
  const [items, setItems] = useState<DeflectionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);

  useEffect(() => {
    // If value is "Not Found", "Not Available", or invalid JSON, initialize with one empty entry
    if (value === "Not Found" || value === "Not Available" || !value || value.trim() === '') {
      setItems([{
        Description: "",
        Combination: "",
        LimitRatio: null,
        Max: null
      }]);
      setError(null);
      return;
    }
    
    try {
      const parsed = JSON.parse(value);
      const itemsArray = Array.isArray(parsed) ? parsed : [parsed];
      setItems(itemsArray);
      setError(null);
    } catch (e) {
      // If parsing fails, initialize with one empty entry instead of showing error
      setItems([{
        Description: "",
        Combination: "",
        LimitRatio: null,
        Max: null
      }]);
      setError(null);
    }
  }, [value]);

  const normalizeLimitRatio = (input: string): string | null => {
    if (!input || input.trim() === '') return null;
    
    // Extract the number from patterns like: 360, 1/360, span/360, l/360, L/360
    const match = input.match(/(?:span|1|l|L)\/(\d+)|^(\d+)$/i);
    if (match) {
      const denominator = match[1] || match[2];
      return `L/${denominator}`;
    }
    
    // If already in L/### format, return as-is
    if (/^L\/\d+$/i.test(input)) {
      return input.toUpperCase();
    }
    
    return input; // Fallback: return the input unchanged
  };

  const handleFieldChange = (itemIndex: number, field: keyof DeflectionItem, newValue: string) => {
    const updatedItems = [...items];
    if (field === 'LimitRatio') {
      // Store the raw input temporarily
      updatedItems[itemIndex][field] = newValue === '' ? null : newValue;
    } else if (field === 'Max') {
      // Max can be null or string
      updatedItems[itemIndex][field] = newValue === '' ? null : newValue;
    } else {
      updatedItems[itemIndex][field] = newValue;
    }
    setItems(updatedItems);
  };

  const handleLimitRatioBlur = (itemIndex: number) => {
    const updatedItems = [...items];
    const currentValue = updatedItems[itemIndex].LimitRatio;
    if (currentValue) {
      updatedItems[itemIndex].LimitRatio = normalizeLimitRatio(currentValue);
      setItems(updatedItems);
    }
  };

  const handleAddEntry = () => {
    const newEntry: DeflectionItem = {
      Description: "",
      Combination: "",
      LimitRatio: null,
      Max: null
    };
    setItems([...items, newEntry]);
  };

  const handleDeleteEntry = (itemIndex: number) => {
    if (items.length <= 1) {
      setError("Cannot delete the last entry. At least one entry is required.");
      return;
    }
    const updatedItems = items.filter((_, index) => index !== itemIndex);
    setItems(updatedItems);
    setDeleteIndex(null);
  };

  const handleSave = () => {
    try {
      const jsonString = JSON.stringify(items);
      onSave(jsonString);
    } catch (e) {
      setError("Failed to save changes");
    }
  };

  if (error) {
    return (
      <div className="space-y-2 p-3 bg-destructive/10 rounded">
        <p className="text-sm text-destructive">{error}</p>
        <Button size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-3 bg-muted/20 rounded">
      {items.map((item, itemIndex) => (
        <div key={itemIndex} className="space-y-3 p-3 bg-background rounded border border-border">
          <div className="flex items-center justify-between mb-2">
            {items.length > 1 && (
              <div className="font-semibold text-sm text-primary">Entry {itemIndex + 1}</div>
            )}
            {items.length > 1 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setDeleteIndex(itemIndex)}
                className="h-7 w-7 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
          
          <div className="space-y-1">
            <Label className="text-xs font-medium text-foreground">Description:</Label>
            <Input
              value={item.Description || ''}
              onChange={(e) => handleFieldChange(itemIndex, 'Description', e.target.value)}
              className="text-xs"
              placeholder="Enter description"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs font-medium text-foreground">Combination:</Label>
            <Input
              value={item.Combination || ''}
              onChange={(e) => handleFieldChange(itemIndex, 'Combination', e.target.value)}
              className="text-xs"
              placeholder="Enter combination"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs font-medium text-foreground">LimitRatio:</Label>
            <Input
              type="text"
              value={item.LimitRatio !== undefined && item.LimitRatio !== null ? item.LimitRatio : ''}
              onChange={(e) => handleFieldChange(itemIndex, 'LimitRatio', e.target.value)}
              onBlur={() => handleLimitRatioBlur(itemIndex)}
              className="text-xs"
              placeholder="e.g., 360 or L/360"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs font-medium text-foreground">Max:</Label>
            <Input
              value={item.Max === null ? '' : (item.Max || '')}
              onChange={(e) => handleFieldChange(itemIndex, 'Max', e.target.value)}
              className="text-xs"
              placeholder="Enter max value"
            />
          </div>
        </div>
      ))}
      
      <div className="flex flex-col gap-3 pt-2">
        <Button size="sm" variant="secondary" onClick={handleAddEntry} className="w-full">
          + New Entry
        </Button>
        
        <div className="flex gap-2">
          <Button size="sm" onClick={handleSave}>
            Save
          </Button>
          <Button size="sm" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>

      <AlertDialog open={deleteIndex !== null} onOpenChange={(open) => !open && setDeleteIndex(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Entry</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete Entry {deleteIndex !== null ? deleteIndex + 1 : ''}? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteIndex !== null && handleDeleteEntry(deleteIndex)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
