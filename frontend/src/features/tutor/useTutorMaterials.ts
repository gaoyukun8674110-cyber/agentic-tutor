import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchStudyMaterials, uploadStudyMaterial, type StudyMaterial } from '../../utils/chatApi';
import { getUserFacingError } from '../../utils/apiClient';
import { deriveSelectedMaterialIds } from '../../utils/materialSelection';
import { tutorQueryKeys } from './tutorQueryKeys';

export function useTutorMaterials() {
  const queryClient = useQueryClient();
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<number[]>([]);
  const [materialError, setMaterialError] = useState<string | null>(null);
  const userTouchedMaterialsRef = useRef(false);
  const pollingIntervalRef = useRef<number | null>(null);

  const materialsQuery = useQuery({
    queryKey: tutorQueryKeys.materials(),
    queryFn: ({ signal }) => fetchStudyMaterials({ signal }),
    retry: false,
  });

  const stopMaterialPolling = useCallback(() => {
    if (pollingIntervalRef.current !== null) {
      window.clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const startMaterialPolling = useCallback(
    (materialId: number) => {
      if (typeof window === 'undefined') return;
      stopMaterialPolling();
      pollingIntervalRef.current = window.setInterval(() => {
        void queryClient
          .fetchQuery({
            queryKey: tutorQueryKeys.materials(),
            queryFn: () => fetchStudyMaterials(),
          })
          .then((items) => {
            const current = items.find((item) => item.id === materialId);
            if (current?.status === 'ready' || current?.status === 'failed') {
              stopMaterialPolling();
            }
          })
          .catch(() => {
            stopMaterialPolling();
          });
      }, 2000);
    },
    [queryClient, stopMaterialPolling],
  );

  const uploadStudyMaterialMutation = useMutation({
    mutationFn: (file: File) => uploadStudyMaterial(file),
    onSuccess: (material) => {
      queryClient.setQueryData<StudyMaterial[]>(tutorQueryKeys.materials(), (items) => [
        material,
        ...(items ?? []).filter((item) => item.id !== material.id),
      ]);
      userTouchedMaterialsRef.current = true;
      setSelectedMaterialIds((ids) => Array.from(new Set([...ids, material.id])));
      setMaterialError(null);
      if (material.status === 'pending') {
        startMaterialPolling(material.id);
      }
    },
    onError: (error) => {
      setMaterialError(getUserFacingError(error));
    },
  });

  const materials = useMemo(() => materialsQuery.data ?? [], [materialsQuery.data]);
  const loadError = useMemo(
    () => (materialsQuery.error ? getUserFacingError(materialsQuery.error) : null),
    [materialsQuery.error],
  );

  useEffect(() => {
    setSelectedMaterialIds((ids) => {
      const materialIds = materials.map((material) => material.id);
      return deriveSelectedMaterialIds(materialIds, ids, userTouchedMaterialsRef.current);
    });
  }, [materials]);

  useEffect(
    () => () => {
      stopMaterialPolling();
    },
    [stopMaterialPolling],
  );

  const toggleMaterialSelection = (materialId: number) => {
    userTouchedMaterialsRef.current = true;
    setSelectedMaterialIds((ids) =>
      ids.includes(materialId) ? ids.filter((id) => id !== materialId) : [...ids, materialId],
    );
  };

  const handleMaterialUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || uploadStudyMaterialMutation.isPending) {
      event.target.value = '';
      return;
    }

    setMaterialError(null);
    uploadStudyMaterialMutation.mutate(file);
    event.target.value = '';
  };

  return {
    materials,
    selectedMaterialIds,
    isLoadingMaterials: materialsQuery.isLoading,
    isUploadingMaterial: uploadStudyMaterialMutation.isPending,
    materialError,
    loadError,
    toggleMaterialSelection,
    handleMaterialUpload,
  };
}
